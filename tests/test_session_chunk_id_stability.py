"""Session window ids follow the exchange, not the file (spec 2026-11-05 §4.2.6-9, A-5)."""

from __future__ import annotations

import hashlib
from pathlib import Path

from vault_graph.indexing.ingestion.document_models import SourceDocument
from vault_graph.indexing.ingestion.document_normalizer import DocumentNormalizer, NormalizedDocument, stable_id
from vault_graph.indexing.ingestion.document_readers import MarkdownDocumentReader
from vault_graph.indexing.ingestion.session_exchange_v2_chunker import drop_duplicate_exchanges

FIXTURES = Path(__file__).parent / "fixtures" / "session_v2"
SESSIONS = "raw/sessions/claude-code"
LONG_SESSION = "44444444-4444-4444-8444-444444444444"
LONG_PART1 = f"{SESSIONS}/2026-11-04-{LONG_SESSION}-part1.md"
LONG_PART3 = f"{SESSIONS}/2026-11-04-{LONG_SESSION}-part3.md"
SUBAGENT_SESSION = "33333333-3333-4333-8333-333333333333"
SUBAGENT = f"{SESSIONS}/2026-11-03-{SUBAGENT_SESSION}-part1.md"


def _normalized(path: str, text: str | None = None, *, vault_id: str = "project") -> NormalizedDocument:
    raw = (FIXTURES / path).read_bytes() if text is None else text.encode("utf-8")
    source = SourceDocument(
        vault_id=vault_id,
        root_path=FIXTURES,
        path=path,
        suffix=".md",
        raw_bytes=raw,
        raw_sha256=hashlib.sha256(raw).hexdigest(),
    )
    return DocumentNormalizer().normalize(MarkdownDocumentReader().read(source))


def _view(document: NormalizedDocument) -> list[tuple[object, ...]]:
    return [
        (
            chunk.chunk_id,
            chunk.text,
            tuple(locator.to_json() for locator in chunk.source_locators),
            chunk.keyword_metadata,
            chunk.parent_key,
        )
        for chunk in document.chunks
    ]


def test_indexing_the_same_file_twice_gives_the_same_ids_text_locators_and_keywords() -> None:
    assert _view(_normalized(LONG_PART1)) == _view(_normalized(LONG_PART1))


def test_window_id_is_built_from_vault_session_exchange_scope_and_window_number() -> None:
    chunks = _normalized(SUBAGENT).chunks

    assert [chunk.chunk_id for chunk in chunks] == [
        stable_id("chunk", "session-exchange-v2-w96", "project", SUBAGENT_SESSION, "u-201", "main", "0"),
        stable_id("chunk", "session-exchange-v2-w96", "project", SUBAGENT_SESSION, "s-301", "subagent:a7f3", "0"),
    ]
    other_vault = _normalized(SUBAGENT, vault_id="other").chunks
    assert {chunk.chunk_id for chunk in other_vault}.isdisjoint({chunk.chunk_id for chunk in chunks})


def test_copy_with_another_renderer_version_part_number_and_path_keeps_the_ids() -> None:
    original = _normalized(LONG_PART1)
    text = (FIXTURES / LONG_PART1).read_text(encoding="utf-8")
    copied = text.replace("renderer: vg-session-md/2.0", "renderer: vg-session-md/2.7").replace(
        "\npart: 1\n", "\npart: 9\n"
    )
    assert copied != text

    moved = _normalized(f"{SESSIONS}/2026-11-04-{LONG_SESSION}-part9.md", copied)

    assert [chunk.chunk_id for chunk in moved.chunks] == [chunk.chunk_id for chunk in original.chunks]
    assert [chunk.text for chunk in moved.chunks] == [chunk.text for chunk in original.chunks]
    assert {chunk.section_path[0] for chunk in moved.chunks} == {"Session 2026-11-04 part9"}


def test_a_new_part_file_does_not_change_the_ids_of_existing_files() -> None:
    before = _normalized(LONG_PART1)

    kept, _ = drop_duplicate_exchanges((before, _normalized(LONG_PART3)))
    after = next(document for document in kept if document.document.path == LONG_PART1)

    assert _view(after) == _view(before)


def test_new_exchanges_in_a_new_part_get_ids_that_existing_files_do_not_use() -> None:
    text = (FIXTURES / LONG_PART3).read_text(encoding="utf-8")
    fresh = text.replace("u-420", "u-499")

    existing = _normalized(LONG_PART1)
    new_part = _normalized(LONG_PART3, fresh)
    kept, warnings = drop_duplicate_exchanges((existing, new_part))

    new_ids = {chunk.chunk_id for chunk in kept[1].chunks}
    assert new_ids
    assert new_ids.isdisjoint({chunk.chunk_id for chunk in existing.chunks})
    assert kept[0] == existing
    assert len(warnings) == 1
