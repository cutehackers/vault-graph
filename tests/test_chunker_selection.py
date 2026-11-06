"""Chunker selection by frontmatter `schema` (spec 2026-11-05 §4.2.6-1·2, A-4)."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

import pytest

from vault_graph.indexing.ingestion.chunker_selection import (
    SESSION_SCHEMA_V1,
    SESSION_SCHEMA_V2,
    chunker_selection,
    embedding_input_for,
    select_chunker,
)
from vault_graph.indexing.ingestion.document_chunking import (
    CHUNKER_VERSION,
    DocumentChunker,
    DocumentWindowChunker,
    contextual_embedding_text,
)
from vault_graph.indexing.ingestion.document_models import ExtractedDocument, SourceDocument
from vault_graph.indexing.ingestion.document_normalizer import DocumentNormalizer
from vault_graph.indexing.ingestion.document_readers import MarkdownDocumentReader

_BODY = """# Title

Intro paragraph with several words that form the first window.

## Section A

- first item
- second item with `code`

```python
print("hello")
```

### Deeper

Deeper paragraph text.

## Section B

Closing words.
"""

# Digest of (chunk_id, text, source_locators, embedding input) per chunk, as produced at abc77e7.
_GOLDEN = {
    "plain": "6c97ddd4c19fd0bb21028040c37134fc3cdca99798d7db9f2389c685099cff22",
    "other-schema": "c993dd85b609e643395851a7d79929b5214e4cc94388ec0e835556895e3faa0e",
    "session-no-schema": "b094db34c9afd9193e503ddd5a8dff3e509afd13c66e88ffbf4586f816a24e98",
}


def _extracted(path: str, frontmatter: str | None) -> ExtractedDocument:
    text = _BODY if frontmatter is None else f"---\n{frontmatter}---\n{_BODY}"
    raw = text.encode("utf-8")
    source = SourceDocument(
        vault_id="default",
        root_path=Path("/vault"),
        path=path,
        suffix=".md",
        raw_bytes=raw,
        raw_sha256=hashlib.sha256(raw).hexdigest(),
    )
    return MarkdownDocumentReader().read(source)


def _digest(extracted: ExtractedDocument) -> str:
    normalized = DocumentNormalizer().normalize(extracted)
    lines = [
        "\x1f".join(
            (
                chunk.chunk_id,
                chunk.text,
                repr(chunk.source_locators),
                contextual_embedding_text(section_path=chunk.section_path, text=chunk.text),
                embedding_input_for(chunk),
            )
        )
        for chunk in normalized.chunks
    ]
    return hashlib.sha256("\x1e".join(lines).encode("utf-8")).hexdigest()


_CASES = {
    "plain": ("wiki/page.md", None),
    "other-schema": ("wiki/page.md", "schema: vault-page/v1\n"),
    "session-no-schema": ("raw/sessions/2026-11-01-x.md", "type: session\nsession_id: s-1\n"),
}


@pytest.mark.parametrize("case", sorted(_CASES))
def test_generic_documents_match_abc77e7_byte_for_byte(case: str) -> None:
    path, frontmatter = _CASES[case]
    extracted = _extracted(path, frontmatter)

    normalized = DocumentNormalizer().normalize(extracted)

    assert normalized.chunks
    assert all(chunk.chunker_version == CHUNKER_VERSION for chunk in normalized.chunks)
    assert all(
        embedding_input_for(chunk) == contextual_embedding_text(section_path=chunk.section_path, text=chunk.text)
        for chunk in normalized.chunks
    )
    assert all(
        chunk.parent_key is None and chunk.parent_locators == () and chunk.keyword_metadata is None
        for chunk in normalized.chunks
    )
    assert normalized.warnings == ()
    assert _digest(extracted) == _GOLDEN[case]


def test_documents_without_session_schema_select_the_window_chunker() -> None:
    for path, frontmatter in _CASES.values():
        selection = chunker_selection(_extracted(path, frontmatter))
        assert isinstance(selection.chunker, DocumentWindowChunker)
        assert selection.warning is None


def test_unknown_session_schema_selects_generic_chunker_with_one_warning() -> None:
    extracted = _extracted("raw/sessions/2026-11-01-x.md", "schema: vault-session/v9\nsession_id: s-1\n")

    assert isinstance(select_chunker(extracted), DocumentWindowChunker)
    normalized = DocumentNormalizer().normalize(extracted)

    assert all(chunk.chunker_version == CHUNKER_VERSION for chunk in normalized.chunks)
    session_warnings = [warning for warning in normalized.warnings if "vault-session/v9" in warning]
    assert len(session_warnings) == 1
    assert "\n" not in session_warnings[0]
    assert session_warnings[0].startswith("unknown_session_schema: ")


@pytest.mark.parametrize("schema", [SESSION_SCHEMA_V1, SESSION_SCHEMA_V2])
def test_known_session_schemas_do_not_warn(schema: str) -> None:
    selection = chunker_selection(_extracted("raw/sessions/2026-11-01-x.md", f"schema: {schema}\n"))

    assert selection.warning is None
    assert isinstance(selection.chunker, DocumentChunker)


def test_embedding_input_for_falls_back_to_contextual_text_for_unregistered_versions() -> None:
    normalized = DocumentNormalizer().normalize(_extracted("wiki/page.md", None))
    legacy = replace(normalized.chunks[1], chunker_version="heading-section-v1")

    assert embedding_input_for(legacy) == contextual_embedding_text(section_path=legacy.section_path, text=legacy.text)


def test_window_chunker_owns_the_contextual_embedding_input() -> None:
    chunker = DocumentWindowChunker()

    assert isinstance(chunker, DocumentChunker)
    expected = contextual_embedding_text(section_path=("A", "B"), text="body")
    assert chunker.embedding_input(("A", "B"), "body") == expected
    assert chunker.embedding_input((), "body") == "body"
