"""`vault-session-facts/v1` attachments become `derived` chunks (spec 2026-11-16 D28, I1, A3, A18).

Contract: docs/contracts/vault-session-facts-v1.md §3 and §5.
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from vault_graph.indexing.ingestion.chunker_selection import (
    CHUNKER_VERSIONS,
    chunker_selection,
    embedding_input_for,
)
from vault_graph.indexing.ingestion.document_models import ExtractedDocument, SourceDocument
from vault_graph.indexing.ingestion.document_normalizer import DocumentNormalizer, NormalizedDocument
from vault_graph.indexing.ingestion.document_readers import MarkdownDocumentReader
from vault_graph.indexing.ingestion.session_facts_chunker import SESSION_FACTS_VERSION, SessionFactsChunker
from vault_graph.indexing.ingestion.session_group import exchange_ranges, reprocess_session_groups, session_group_key
from vault_graph.indexing.metadata_indexer import INDEX_CODE_PARTS, MetadataIndexer
from vault_graph.operation.scope.vault_catalog import VaultCatalog, VaultCatalogEntry
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore

FIXTURES = Path(__file__).parent / "fixtures" / "session_v2"
SESSION_ID = "11111111-1111-4111-8111-111111111111"
PART = f"raw/sessions/claude-code/2026-11-01-{SESSION_ID}-part1.md"
FACTS = f"raw/sessions/claude-code/2026-11-01-{SESSION_ID}-part1.facts.md"


def facts_text(*, schema: str = "vault-session-facts/v1", body: str | None = None) -> str:
    if body is None:
        body = (
            "- 2026-11-01 The user fixed the failing test in src/app.py. (exchange u-001)\n"
            "- 2026-10-30 사용자는 데이터베이스 비밀번호를 .env에 둔다. (exchange u-001)\n"
        )
    return (
        "---\n"
        f"schema: {schema}\n"
        "agent: claude-code\n"
        f'session_id: "{SESSION_ID}"\n'
        "part: 1\n"
        f"source: {PART}\n"
        'source_sha256: "abc"\n'
        "extractor: claude\n"
        "model: claude-sonnet-5-5\n"
        'generated_at: "2026-11-16T03:00:00Z"\n'
        "fact_count: 2\n"
        "---\n"
        "\n"
        f"{body}"
    )


def extracted(path: str, text: str) -> ExtractedDocument:
    raw = text.encode("utf-8")
    source = SourceDocument(
        vault_id="main",
        root_path=FIXTURES,
        path=path,
        suffix=".md",
        raw_bytes=raw,
        raw_sha256=hashlib.sha256(raw).hexdigest(),
    )
    return MarkdownDocumentReader().read(source)


def normalized(text: str) -> NormalizedDocument:
    return DocumentNormalizer().normalize(extracted(FACTS, text))


def test_v1_attachment_selects_the_session_facts_chunker_without_a_warning() -> None:
    selection = chunker_selection(extracted(FACTS, facts_text()))

    assert isinstance(selection.chunker, SessionFactsChunker)
    assert selection.warning is None
    assert SESSION_FACTS_VERSION in CHUNKER_VERSIONS
    assert SESSION_FACTS_VERSION in INDEX_CODE_PARTS


def test_each_fact_line_is_one_derived_chunk_keyed_to_the_original_exchange() -> None:
    item = normalized(facts_text())

    assert item.warnings == ()
    assert [chunk.chunker_version for chunk in item.chunks] == [SESSION_FACTS_VERSION] * 2
    assert [chunk.parent_key for chunk in item.chunks] == [f"{SESSION_ID}:u-001"] * 2
    assert [chunk.text for chunk in item.chunks] == [
        "The user fixed the failing test in src/app.py.",
        "사용자는 데이터베이스 비밀번호를 .env에 둔다.",
    ]
    assert [(chunk.started_at, chunk.ended_at) for chunk in item.chunks] == [
        ("2026-11-01T00:00:00Z", "2026-11-01T23:59:59Z"),
        ("2026-10-30T00:00:00Z", "2026-10-30T23:59:59Z"),
    ]
    lines = facts_text().split("\n")
    for chunk in item.chunks:
        line = int(dict(chunk.source_locators[0].coordinates)["line"])
        assert chunk.text in lines[line - 1]
    assert len({chunk.chunk_id for chunk in item.chunks}) == 2
    expected_input = "Session: 2026-11-01\n\nThe user fixed the failing test in src/app.py."
    assert embedding_input_for(item.chunks[0]) == expected_input


def test_attachment_is_not_a_session_file() -> None:
    document = extracted(FACTS, facts_text())

    assert session_group_key(document.frontmatter.data) is None
    assert exchange_ranges(document) == {}
    item = normalized(facts_text())
    result, warnings = reprocess_session_groups((item,), {})
    assert result == (item,)
    assert warnings == ()


def test_malformed_lines_are_skipped_with_one_warning() -> None:
    body = (
        "- 2026-11-01 Good fact. (exchange u-001)\n"
        "- 2026-13-40 Bad date. (exchange u-001)\n"
        "- 2026-11-01 No exchange marker.\n"
        "free text\n"
        "\n"
        "- 2026-11-02 Second good fact. (exchange u-002)\n"
    )
    item = normalized(facts_text(body=body))

    assert [chunk.text for chunk in item.chunks] == ["Good fact.", "Second good fact."]
    assert [chunk.parent_key for chunk in item.chunks] == [f"{SESSION_ID}:u-001", f"{SESSION_ID}:u-002"]
    assert len(item.warnings) == 1
    assert item.warnings[0].startswith(f"session_facts_line_invalid: {FACTS}: 3 lines")


def test_unknown_facts_version_is_not_indexed_with_one_warning() -> None:
    item = normalized(facts_text(schema="vault-session-facts/v2"))

    assert item.chunks == ()
    assert item.warnings == (f"unknown_session_facts_schema: {FACTS} has schema vault-session-facts/v2; not indexed",)


def _index(tmp_path: Path, root: Path, name: str) -> tuple[SQLiteMetadataStore, tuple[str, ...]]:
    catalog = VaultCatalog.from_entries(
        entries=[VaultCatalogEntry.from_root(vault_id="main", root_path=root)], active_vault_id="main"
    )
    store = SQLiteMetadataStore(tmp_path / name / "metadata.sqlite3", initialize=True)
    plan = MetadataIndexer(catalog=catalog, metadata_store=store).apply(scope=catalog.default_scope())
    return store, plan.warnings


def _vault(tmp_path: Path, name: str) -> Path:
    root = tmp_path / name
    target = root / PART
    target.parent.mkdir(parents=True)
    shutil.copyfile(FIXTURES / PART, target)
    return root


def test_part_windows_are_byte_identical_when_an_attachment_sits_next_to_the_part(tmp_path: Path) -> None:
    alone = _vault(tmp_path, "alone")
    attached = _vault(tmp_path, "attached")
    (attached / FACTS).write_text(facts_text(), encoding="utf-8")

    alone_store, _ = _index(tmp_path, alone, "alone-index")
    attached_store, warnings = _index(tmp_path, attached, "attached-index")

    def windows(store: SQLiteMetadataStore) -> list[tuple[object, ...]]:
        scope = VaultCatalog.from_entries(
            entries=[VaultCatalogEntry.from_root(vault_id="main", root_path=tmp_path)], active_vault_id="main"
        ).default_scope()
        return sorted(
            (chunk.chunk_id, chunk.text, chunk.source_locators, embedding_input_for(chunk), chunk.parent_key)
            for chunk in store.list_chunks(scope)
            if chunk.path == PART
        )

    assert windows(alone_store)
    assert windows(attached_store) == windows(alone_store)
    assert not any(FACTS in warning for warning in warnings)

    with attached_store.connect_for_tests() as connection:
        groups = dict(connection.execute("SELECT path, session_group_key FROM documents").fetchall())
        facts = connection.execute(
            "SELECT parent_key, chunker_version, started_at FROM chunks WHERE path = ? ORDER BY document_order",
            (FACTS,),
        ).fetchall()
    assert groups[PART] == f"claude-code:{SESSION_ID}"
    assert groups[FACTS] is None
    assert [tuple(row) for row in facts] == [
        (f"{SESSION_ID}:u-001", SESSION_FACTS_VERSION, "2026-11-01T00:00:00Z"),
        (f"{SESSION_ID}:u-001", SESSION_FACTS_VERSION, "2026-10-30T00:00:00Z"),
    ]
    parent_keys = {window[4] for window in windows(attached_store)}
    assert {row[0] for row in facts} <= parent_keys
