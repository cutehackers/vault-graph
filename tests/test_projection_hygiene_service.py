from dataclasses import replace
from pathlib import Path

from tests.test_sqlite_metadata_store import make_chunk, make_document
from vault_graph.app.projection_hygiene_service import ProjectionHygieneService
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore


def test_hygiene_report_proves_single_body_and_zero_dangling_refs(tmp_path: Path) -> None:
    metadata_path = tmp_path / "metadata.sqlite3"
    store = SQLiteMetadataStore(metadata_path, initialize=True)
    first_document = make_document("default", "wiki/first.md", "same")
    second_document = make_document("default", "wiki/second.md", "same")
    first_chunk = replace(
        make_chunk("default", first_document.document_id, first_document.path, text="same"),
        content_hash="shared-body",
        provenance_family_id="family:first",
    )
    second_chunk = replace(
        make_chunk("default", second_document.document_id, second_document.path, text="same"),
        content_hash="shared-body",
        provenance_family_id="family:second",
    )
    store.apply_metadata_revision(
        index_revision="metadata-1",
        documents=[first_document, second_document],
        chunks=[first_chunk, second_chunk],
        tombstones=[],
    )

    report = ProjectionHygieneService(
        metadata_path=metadata_path,
        vector_path=tmp_path / "vector",
        graph_path=tmp_path / "graph.sqlite3",
    ).audit(scope=QueryScope(vault_ids=("default",), content_scopes=("wiki",)))

    assert report.canonical_blob_count == 1
    assert report.plaintext_amplification == 1.0
    assert report.persisted_search_projection_plaintext_bytes == 0
    assert report.dangling_keyword_refs == 0
    assert report.dangling_vector_refs == 0
    assert report.dangling_graph_refs == 0
