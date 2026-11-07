"""The page card is a search unit, not page text (spec 2026-11-05 §10.5).

Every reader that rebuilds or quotes a page body from stored chunks leaves the card out. The card repeats
frontmatter values, so card-only text ("Map of the wiki.") must not show up in a page body.
"""

from __future__ import annotations

from pathlib import Path

from tests.test_metadata_chunk_kind import _SCOPE, _store
from vault_graph.context.memory.memory_source_reader import MemorySourceReader
from vault_graph.interface.composition.read_only_service_factory import metadata_body_reader
from vault_graph.interface.mcp.mcp_uri import parse_mcp_resource_uri
from vault_graph.interface.mcp.metadata_resource_reader import MetadataResourceReader
from vault_graph.operation.scope.vault_catalog import VaultCatalog, VaultCatalogEntry
from vault_graph.retrieval.search.context_expansion import ContextExpander

CARD_ONLY_TEXT = "Map of the wiki."


def test_stored_page_has_a_card_with_text_the_body_does_not_have(tmp_path: Path) -> None:
    store, normalized = _store(tmp_path)
    chunks = store.list_document_chunks(vault_id="default", document_id=normalized.document.document_id)

    assert [chunk.chunk_kind for chunk in chunks] == ["page_card", "body", "template"]
    assert CARD_ONLY_TEXT in chunks[0].text
    assert all(CARD_ONLY_TEXT not in chunk.text for chunk in chunks[1:])


def test_mcp_page_resource_body_and_evidence_leave_out_the_card(tmp_path: Path) -> None:
    store, normalized = _store(tmp_path)
    root = tmp_path / "vault"
    root.mkdir()
    catalog = VaultCatalog.from_entries(
        entries=(VaultCatalogEntry.from_root(vault_id="default", root_path=root, content_scopes=("wiki",)),),
        active_vault_id="default",
    )
    reader = MetadataResourceReader(catalog=catalog, metadata_store=store)

    body = reader.read_page(parse_mcp_resource_uri("vault://default/pages/wiki%2Foverview.md", catalog=catalog))

    assert CARD_ONLY_TEXT not in body.text
    assert body.text.startswith("## Areas")
    assert body.metadata["chunk_count"] == 2
    evidence = body.metadata["evidence_refs"]
    assert isinstance(evidence, list) and len(evidence) == 2


def test_recall_body_reader_leaves_out_the_card(tmp_path: Path) -> None:
    store, normalized = _store(tmp_path)

    text = metadata_body_reader(store)("default", normalized.document.document_id)

    assert CARD_ONLY_TEXT not in text
    assert "The wiki covers retrieval" in text


def test_memory_source_reader_leaves_out_the_card(tmp_path: Path) -> None:
    store, normalized = _store(tmp_path)
    card = normalized.chunks[0]

    read = MemorySourceReader(metadata_store=store).read_document(document=normalized.document, max_evidence_chunks=5)

    assert CARD_ONLY_TEXT not in read.body_excerpt
    assert card.chunk_id not in {heading.chunk_id for heading in read.headings}
    assert card.chunk_id not in {evidence.chunk_id for evidence in read.evidence}


def test_context_expansion_does_not_add_the_card_as_a_neighbor(tmp_path: Path) -> None:
    store, normalized = _store(tmp_path)
    card, body, _template = store.list_document_chunks(vault_id="default", document_id=normalized.document.document_id)

    expansion = ContextExpander(metadata_store=store).expand(
        matched_chunk=body, scope=_SCOPE, max_tokens=1000, neighbor_radius=2
    )

    assert card.chunk_id not in expansion.context_chunk_ids
