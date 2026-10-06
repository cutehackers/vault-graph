"""Measure the document backend through Vault Graph's actual indexing and read factories.

Run from the repository root:
    uv run --python 3.12 python -m tests.benchmarks.measure_document_graph_backend

"Cold open" means a fresh read-only store object in one process. It does not
flush the operating system page cache. Timed samples exclude result validation
and close; tracemalloc runs separately to avoid changing the latency samples.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import statistics
import sys
import tempfile
import time
import tracemalloc
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pytest import MonkeyPatch
from typer.testing import CliRunner

from tests.test_cli_graph_indexing import (
    _ConfiguredDeterministicTextEmbeddings,
    _deterministic_text_embeddings,
    write_page,
)
from vault_graph.app.catalog_service import CatalogService
from vault_graph.app.graph_store_factory import open_graph_store, selected_graph_backend
from vault_graph.app.read_only_service_factory import ReadOnlyServiceFactory
from vault_graph.cli.main import app
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore

DOCUMENT_COUNT = 1000
DOCUMENT_BYTES = 4096
WARMUPS = 3
SAMPLES = 20
TARGETS = {"cold_open_p95_ms": 2000.0, "warm_related_p95_ms": 200.0, "python_peak_mib": 128.0}
REPORT_PATH = Path("docs/design/reports/2026-10-04-document-graph-backend-performance.json")


def _fingerprints(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }


def _body(index: int) -> str:
    title = "Target" if index == 0 else f"Page {index:04d}"
    link = "Target evidence.\n" if index == 0 else "See [[target]].\n"
    prefix = f"---\ntitle: {title}\ntags: [shared]\n---\n# Evidence\n{link}"
    padding = "x" * (DOCUMENT_BYTES - len(prefix.encode("utf-8")) - 1)
    return prefix + padding + "\n"


def _index_fixture(root: Path, patch: MonkeyPatch) -> tuple[Path, Path]:
    patch.setattr("vault_graph.cli.main._text_embeddings", _deterministic_text_embeddings)

    def embeddings(_self: object, config: object) -> _ConfiguredDeterministicTextEmbeddings:
        return _deterministic_text_embeddings(config)

    patch.setattr(ReadOnlyServiceFactory, "_search_text_embeddings", embeddings)
    vault = root / "vault"
    for index in range(DOCUMENT_COUNT):
        path = "wiki/target.md" if index == 0 else f"wiki/page-{index:04d}.md"
        write_page(vault, path, _body(index))
    home = root / "state"
    runner = CliRunner()
    for args in (
        ["init", "--vault", str(vault), "--graph-home", str(home)],
        ["index", "--graph-home", str(home), "--full"],
        ["index", "--graph-home", str(home), "--graph-backend", "document"],
    ):
        result = runner.invoke(app, args)
        if result.exit_code:
            raise RuntimeError(f"CLI indexing failed: {args[0]}: {result.output}")
    return vault, home


def _percentile(values: list[float], proportion: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * proportion
    lower = int(position)
    return ordered[lower] + (ordered[min(lower + 1, len(ordered) - 1)] - ordered[lower]) * (position - lower)


def _samples[T](action: Callable[[], T], validate: Callable[[T], None]) -> dict[str, Any]:
    for _ in range(WARMUPS):
        validate(action())
    values: list[float] = []
    for _ in range(SAMPLES):
        start = time.perf_counter_ns()
        result = action()
        values.append((time.perf_counter_ns() - start) / 1_000_000)
        validate(result)
    return {
        "warmups": WARMUPS,
        "sample_count": SAMPLES,
        "samples_ms": [round(value, 6) for value in values],
        "p50_ms": round(statistics.median(values), 6),
        "p95_ms": round(_percentile(values, 0.95), 6),
    }


def _peak[T](action: Callable[[], T], validate: Callable[[T], None]) -> int:
    tracemalloc.start()
    try:
        validate(action())
        _, peak = tracemalloc.get_traced_memory()
        return peak
    finally:
        tracemalloc.stop()


def _measure(home: Path) -> dict[str, Any]:
    catalog_service = CatalogService(graph_home_path=home)
    catalog = catalog_service.load_catalog()
    scope = catalog.default_scope()
    if selected_graph_backend(catalog_service) != "document":
        raise AssertionError("document backend is not selected")
    metadata = SQLiteMetadataStore(catalog_service.metadata_path, initialize=False)

    def open_store() -> Any:
        return open_graph_store(catalog_service, metadata_store=metadata)

    def validate_store(store: Any) -> None:
        try:
            health = store.health()
            if not health.ok:
                raise AssertionError(f"document graph store is unhealthy: {health}")
        finally:
            store.close()

    cold = _samples(open_store, validate_store)
    cold_peak = _peak(open_store, validate_store)
    service = ReadOnlyServiceFactory(graph_home_path=home).open_graph_retrieval_service()

    def related() -> Any:
        return service.related(target="Page 0500", requested_scope=scope, limit=10, output_format="json")

    def validate_related(response: Any) -> None:
        if response.result_count < 1 or not response.projection_build_id:
            raise AssertionError("related query did not traverse the indexed graph")

    warm = _samples(related, validate_related)
    warm_peak = _peak(related, validate_related)
    store = open_store()
    try:
        manifest = store.current_manifest((scope,))
    finally:
        store.close()
    peak = max(cold_peak, warm_peak)
    return {
        "workload": {
            "vault_document_count": DOCUMENT_COUNT,
            "bytes_per_document": DOCUMENT_BYTES,
            "total_source_bytes": DOCUMENT_COUNT * DOCUMENT_BYTES,
            "graph_entities": len(manifest.entity_rows),
            "graph_relationships": len(manifest.relationship_rows),
            "related_target": "Page 0500",
        },
        "latency": {"cold_read_only_store_open": cold, "warm_related_query": warm},
        "python_allocation_peak_bytes": {"cold_open": cold_peak, "warm_related": warm_peak, "maximum": peak},
        "targets": TARGETS,
        "passed": {
            "cold_open_p95": cold["p95_ms"] <= TARGETS["cold_open_p95_ms"],
            "warm_related_p95": warm["p95_ms"] <= TARGETS["warm_related_p95_ms"],
            "python_peak": peak / 1024**2 <= TARGETS["python_peak_mib"],
        },
    }


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="vault-graph-document-benchmark-") as temporary:
        with MonkeyPatch.context() as patch:
            vault, home = _index_fixture(Path(temporary), patch)
            source_before, state_before = _fingerprints(vault), _fingerprints(home)
            result = _measure(home)
            result["read_only_checks"] = {
                "vault_unchanged": _fingerprints(vault) == source_before,
                "data_home_unchanged": _fingerprints(home) == state_before,
            }
    result["environment"] = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "machine": platform.machine(),
        "graph_document_version": importlib.metadata.version("nolemy-graph-document"),
        "graph_search_version": importlib.metadata.version("nolemy-graph-search"),
        "timing_clock": "time.perf_counter_ns",
        "cold_open_definition": "new read-only store object in one process; OS page cache retained",
        "memory_method": "separate tracemalloc run per operation; maximum peak reported",
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {"passed": result["passed"], "latency": result["latency"], "read_only_checks": result["read_only_checks"]}
        )
    )
    if not all(result["passed"].values()) or not all(result["read_only_checks"].values()):
        raise SystemExit("Document graph backend did not meet its performance or read-only acceptance criteria")


if __name__ == "__main__":
    main()
