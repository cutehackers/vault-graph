"""Measure existing preparation and bounded evidence-owner lookup separately.

Run: uv run --no-sync python -m tests.benchmarks.measure_evidence_linking
Cold open creates a new document store in one process with OS caches retained.
Result validation and store close are outside timed samples. No new SLA applies.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import sys
import tempfile
from pathlib import Path
from typing import Any

from pytest import MonkeyPatch

from tests.benchmarks.measure_document_graph_backend import (
    DOCUMENT_BYTES,
    DOCUMENT_COUNT,
    _fingerprints,
    _index_fixture,
    _samples,
)
from vault_graph.app.graph_store_factory import open_graph_store, selected_graph_backend
from vault_graph.app.read_only_service_factory import ReadOnlyServiceFactory
from vault_graph.graph.graph_contracts import current_graph_extraction_spec
from vault_graph.graph.graph_readiness import GraphReadiness
from vault_graph.projection_readiness.graph_readiness_service import ReadOnlyGraphReadiness
from vault_graph.storage.interfaces.evidence_owner_lookup import EvidenceOwnerRecord
from vault_graph.storage.local.document_graph_store import DocumentGraphStore
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore
from vault_graph.vault_adapter.evidence_linking import GraphLinksRequest, GraphLinksResult
from vault_graph.vault_scope.catalog_service import CatalogService

REPORT_PATH = Path("docs/design/reports/2026-10-15-evidence-linking-performance.json")


def _tree_digest(root: Path) -> dict[str, object]:
    fingerprints = _fingerprints(root)
    return {
        "file_count": len(fingerprints),
        "sha256_of_sorted_path_hashes": hashlib.sha256(
            json.dumps(fingerprints, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    }


def _measure(home: Path) -> dict[str, Any]:
    catalog_service = CatalogService(graph_home_path=home)
    scope = catalog_service.load_catalog().default_scope()
    assert selected_graph_backend(catalog_service) == "document"
    metadata = SQLiteMetadataStore(catalog_service.metadata_path, initialize=False)
    document = next(item for item in metadata.list_documents(scope) if item.path == "wiki/page-0500.md")
    chunks = metadata.list_document_chunks(vault_id=document.vault_id, document_id=document.document_id)
    assert chunks
    key = (document.vault_id, document.document_id, chunks[0].chunk_id)

    def open_store() -> DocumentGraphStore:
        store = open_graph_store(catalog_service, metadata_store=metadata)
        assert isinstance(store, DocumentGraphStore)
        return store

    def validate_store(store: DocumentGraphStore) -> None:
        try:
            assert store.health().ok
        finally:
            store.close()

    cold = _samples(open_store, validate_store)
    store = open_store()
    linker = ReadOnlyServiceFactory(graph_home_path=home).open_evidence_linker()
    try:
        readiness = ReadOnlyGraphReadiness(
            metadata_store=metadata, graph_store=store, expected_spec=current_graph_extraction_spec()
        )

        def check_readiness() -> GraphReadiness:
            return readiness.check(requested_scope=scope, actual_scopes=(scope,))

        def validate_readiness(result: GraphReadiness) -> None:
            assert result.freshness == "fresh", result

        preparation = _samples(check_readiness, validate_readiness)

        def lookup() -> tuple[EvidenceOwnerRecord, ...]:
            return store.lookup_evidence_owners(
                vault_id=key[0],
                document_id=key[1],
                chunk_id=key[2],
                scopes=(scope,),
                include_cross_vault=False,
                limit=11,
            )

        expected_rows = lookup()
        assert 0 < len(expected_rows) <= 11

        def validate_lookup(rows: tuple[EvidenceOwnerRecord, ...]) -> None:
            assert rows == expected_rows

        bounded_lookup = _samples(lookup, validate_lookup)
        request = GraphLinksRequest((key,), (scope,), False, max_keys=1, limit=10)
        expected_links = linker.find_graph_links(request)
        assert expected_links.coverage == "complete", expected_links
        assert expected_links.stop_reason == "completed", expected_links
        assert expected_links.links
        assert tuple(link.owner for link in expected_links.links) == tuple(
            (row.owner_kind, row.owner_vault_id, row.owner_id) for row in expected_rows
        )

        def full_linking() -> GraphLinksResult:
            return linker.find_graph_links(request)

        def validate_linking(result: GraphLinksResult) -> None:
            assert result == expected_links

        full = _samples(full_linking, validate_linking)
        manifest = store.current_manifest((scope,))
        return {
            "contract": "SEL-20261015 section 10",
            "workload": {
                "backend": "document",
                "vault_document_count": DOCUMENT_COUNT,
                "bytes_per_document": DOCUMENT_BYTES,
                "total_source_bytes": DOCUMENT_COUNT * DOCUMENT_BYTES,
                "graph_entities": len(manifest.entity_rows),
                "graph_relationships": len(manifest.relationship_rows),
                "source_path": document.path,
                "evidence_key": key,
                "requested_key_count": 1,
                "direct_lookup_limit": 11,
                "linker_result_limit": 10,
                "indexing_path": "CLI init, index --full, index --graph-backend document",
                "embeddings": "deterministic fixture adapter, no external model or network",
            },
            "latency": {
                "existing_document_backend_cold_open": cold,
                "existing_full_scope_readiness": preparation,
                "new_bounded_owner_lookup": bounded_lookup,
                "full_factory_linker_request": full,
            },
            "returned": {
                "direct_owner_rows": len(expected_rows),
                "linker_links": len(expected_links.links),
                "linker_outcomes": len(expected_links.outcomes),
                "coverage": expected_links.coverage,
                "stop_reason": expected_links.stop_reason,
                "source_revision_count": len(expected_links.source_revisions),
            },
            "measurement_scope": {
                "cold_open": "fresh store object per sample; excludes validation and close; OS page cache retained",
                "readiness": "existing full-scope manifest and evidence validation on an open store",
                "bounded_lookup": "new direct owner lookup on an open store; excludes readiness and lineage scans",
                "full_linker": "actual factory request with readiness, before/after lineage and evidence checks",
                "factory_open": "outside full-linker timed samples; document cold-open measured separately",
                "sla": "no new numerical SLA or throughput target",
            },
        }
    finally:
        store.close()
        # The factory exposes a lookup facade without a public close method.
        lookup_store = linker._lookup
        if isinstance(lookup_store, DocumentGraphStore):
            lookup_store.close()


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="vault-graph-evidence-linking-") as temporary:
        with MonkeyPatch.context() as patch:
            vault, home = _index_fixture(Path(temporary), patch)
            before = {"vault": _tree_digest(vault), "data_home": _tree_digest(home)}
            result = _measure(home)
            after = {"vault": _tree_digest(vault), "data_home": _tree_digest(home)}
            result["read_only_checks"] = {
                "before": before,
                "after": after,
                "vault_unchanged": before["vault"] == after["vault"],
                "data_home_unchanged": before["data_home"] == after["data_home"],
            }
            assert before == after, result["read_only_checks"]
    result["environment"] = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "machine": platform.machine(),
        "graph_document_version": importlib.metadata.version("nolemy-graph-document"),
        "graph_search_version": importlib.metadata.version("nolemy-graph-search"),
        "timing_clock": "time.perf_counter_ns",
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "latency": result["latency"],
                "returned": result["returned"],
                "read_only_checks": result["read_only_checks"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
