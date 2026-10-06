"""Measure graph modules on fixed workloads without applying performance gates.

Run from the repository root with the three packages available, for example:

    PYTHONPATH=src:packages/graph-search/src:packages/graph-document/src \
      uv run --python 3.12 python tests/benchmarks/measure_graph_modules.py

The JSON report contains workload sizes, raw samples, p50/p95 latency, and
separate traced-memory peaks. No source documents or external services are used.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import platform
import statistics
import sys
import tempfile
import time
import tracemalloc
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

from graph_document import (
    Document,
    DocumentFeatures,
    EvidenceLocation,
    ExtractionProfile,
    GraphDocument,
    LocatedValue,
    ReadLimits,
)
from graph_document import (
    GraphLimits as DocumentLimits,
)
from graph_document.search_bridge import prepare_search
from graph_search import (
    Edge,
    GraphSnapshot,
    PathOptions,
    SearchOptions,
    graph_search,
    search_paths,
)
from graph_search import (
    GraphLimits as SearchLimits,
)

from vault_graph.projection.graph_projection import GraphProjectionEdge, GraphProjectionInput, GraphProjectionNode
from vault_graph.projection.rustworkx_projection import RustworkxGraphProjection
from vault_graph.projection.vault_graph_projection_adapter import VaultGraphProjectionAdapter

BODY_MARKER = "PRIVATE_BODY_MARKER"
BODY = BODY_MARKER + "x" * (4096 - len(BODY_MARKER))
DOCUMENT_COUNT = 1000
READ_LIMITS = ReadLimits(2000, 3000, 6000, 1100, 8_000_000)
DOCUMENT_LIMITS = DocumentLimits(1000, 8192, 8_000_000, 2000, 3000, 6000, 256)
SEARCH_LIMITS = SearchLimits(2000, 3000, 256, 500_000)
PROFILE = ExtractionProfile()


def _percentile(values: list[float], percentage: float) -> float:
    ordered = sorted(values)
    rank = (len(ordered) - 1) * percentage
    lower = int(rank)
    fraction = rank - lower
    return ordered[lower] + (ordered[min(lower + 1, len(ordered) - 1)] - ordered[lower]) * fraction


def _summary(values: list[float]) -> dict[str, Any]:
    return {
        "sample_count": len(values),
        "p50_ms": round(statistics.median(values), 6),
        "p95_ms": round(_percentile(values, 0.95), 6),
        "samples_ms": [round(value, 6) for value in values],
    }


def _samples[T](
    action: Callable[[], T],
    validate: Callable[[T], None],
    *,
    count: int,
    warmups: int,
) -> dict[str, Any]:
    for _ in range(warmups):
        validate(action())
    durations: list[float] = []
    for _ in range(count):
        start = time.perf_counter_ns()
        result = action()
        durations.append((time.perf_counter_ns() - start) / 1_000_000)
        validate(result)
    return _summary(durations)


def _peak[T](action: Callable[[], T], validate: Callable[[T], None]) -> int:
    tracemalloc.start()
    try:
        validate(action())
        _, peak = tracemalloc.get_traced_memory()
        return peak
    finally:
        tracemalloc.stop()


def _search_star() -> GraphSnapshot:
    return GraphSnapshot.build(
        node_ids=("s", *(f"n{i:03d}" for i in range(500))),
        edges=tuple(Edge(f"e{i:03d}", "s", f"n{i:03d}") for i in range(500)),
        limits=SearchLimits(501, 500, 32, 10_000),
    )


def _search_parallel() -> GraphSnapshot:
    return GraphSnapshot.build(
        node_ids=("a", "b", "c"),
        edges=(
            *(Edge(f"ab{i:03d}", "a", "b") for i in range(250)),
            *(Edge(f"bc{i:03d}", "b", "c") for i in range(250)),
        ),
        limits=SearchLimits(3, 500, 32, 10_000),
    )


def _enumerate_parallel(snapshot: GraphSnapshot) -> tuple[int, str, int]:
    with search_paths(snapshot, source_id="a", options=PathOptions("outbound", 2, 62_750, 62_750)) as traversal:
        count = sum(1 for _ in traversal)
    assert traversal.summary is not None
    return count, traversal.summary.stop_reason, traversal.summary.examined_edges


def _vault_request(*, star: bool) -> GraphProjectionInput:
    if star:
        nodes = (GraphProjectionNode("v", "s", "Concept", "s", "s"),) + tuple(
            GraphProjectionNode("v", f"n{i:03d}", "Concept", f"n{i:03d}", f"n{i:03d}") for i in range(500)
        )
        relationships = tuple(
            GraphProjectionEdge(
                "v", "s", "v", f"n{i:03d}", f"e{i:03d}", "mentions", "stated", 1.0, (f"ev{i:03d}",), "rev1"
            )
            for i in range(500)
        )
        depth = 1
    else:
        nodes = tuple(
            GraphProjectionNode("v", identifier, "Concept", identifier, identifier) for identifier in ("a", "b", "c")
        )
        relationships = (
            *(
                GraphProjectionEdge(
                    "v", "a", "v", "b", f"ab{i:03d}", "mentions", "stated", 1.0, (f"evab{i:03d}",), "rev1"
                )
                for i in range(250)
            ),
            *(
                GraphProjectionEdge(
                    "v", "b", "v", "c", f"bc{i:03d}", "mentions", "stated", 1.0, (f"evbc{i:03d}",), "rev1"
                )
                for i in range(250)
            ),
        )
        depth = 2
    return GraphProjectionInput(
        seeds=(nodes[0],),
        nodes=nodes,
        relationships=relationships,
        actual_scope_keys=("v:wiki:local",),
        source_graph_revisions=("rev1",),
        max_depth=depth,
        direction="out",
        relationship_types=("mentions",),
        statuses=("stated",),
        include_cross_vault=False,
        limit=50,
        edge_limit=500,
    )


def _documents() -> tuple[Document, ...]:
    return tuple(
        Document(
            document_id=f"doc{i:04d}",
            source_revision="v1",
            title=f"Document {i:04d}",
            text=BODY,
            features=DocumentFeatures(
                tags=(
                    LocatedValue("shared-one", EvidenceLocation("tag-one")),
                    LocatedValue("shared-two", EvidenceLocation("tag-two")),
                ),
            ),
            source_locator=f"source://doc{i:04d}",
        )
        for i in range(DOCUMENT_COUNT)
    )


def _changed(document: Document) -> Document:
    return replace(document, source_revision="v2", text="Y" + document.text[1:])


def _new_store(path: Path) -> GraphDocument:
    return GraphDocument.open(path, mode="create", limits=DOCUMENT_LIMITS, profile=PROFILE)


def _assert_document_graph(read: Any, *, selected: bool) -> None:
    expected = (3, 2, 5, 1) if selected else (1002, 2000, 5000, 1000)
    observed = (len(read.nodes), len(read.edges), len(read.evidence), len(read.documents))
    if observed != expected:
        raise AssertionError(f"document graph counts {observed} != {expected}")


def _assert_no_plaintext(path: Path) -> None:
    if BODY_MARKER.encode() in path.read_bytes():
        raise AssertionError("Document plaintext was stored in the graph DB")


def _document_writes(root: Path, documents: tuple[Document, ...], count: int) -> dict[str, Any]:
    initial_times: list[float] = []
    changed_times: list[float] = []
    for sample in range(count):
        path = root / f"write-{sample}.sqlite"
        with _new_store(path) as store:
            start = time.perf_counter_ns()
            first = store.update_documents(documents, collection_id="bench", expected_revision=0)
            initial_times.append((time.perf_counter_ns() - start) / 1_000_000)
            if first.graph_revision != 1 or len(first.changed_document_ids) != DOCUMENT_COUNT:
                raise AssertionError("Initial document index result differs")
            start = time.perf_counter_ns()
            second = store.update_documents((_changed(documents[0]),), collection_id="bench", expected_revision=1)
            changed_times.append((time.perf_counter_ns() - start) / 1_000_000)
            if second.graph_revision != 2 or len(second.changed_document_ids) != 1:
                raise AssertionError("Single-document update result differs")
        _assert_no_plaintext(path)
    return {"initial_index": _summary(initial_times), "single_changed_document_index": _summary(changed_times)}


def _document_write_peaks(root: Path, documents: tuple[Document, ...]) -> dict[str, int]:
    def expect_revision_one(result: Any) -> None:
        if result.graph_revision != 1:
            raise AssertionError("Initial index revision differs")

    def expect_revision_two(result: Any) -> None:
        if result.graph_revision != 2:
            raise AssertionError("Changed index revision differs")

    initial_path = root / "peak-initial.sqlite"
    with _new_store(initial_path) as store:
        initial_peak = _peak(
            lambda: store.update_documents(documents, collection_id="bench", expected_revision=0),
            expect_revision_one,
        )
    _assert_no_plaintext(initial_path)
    changed_path = root / "peak-changed.sqlite"
    with _new_store(changed_path) as store:
        store.update_documents(documents, collection_id="bench", expected_revision=0)
        changed_peak = _peak(
            lambda: store.update_documents((_changed(documents[0]),), collection_id="bench", expected_revision=1),
            expect_revision_two,
        )
    _assert_no_plaintext(changed_path)
    return {"initial_index": initial_peak, "single_changed_document_index": changed_peak}


def measure(*, read_samples: int, write_samples: int, warmups: int) -> dict[str, Any]:
    star = _search_star()
    parallel = _search_parallel()
    search_options = SearchOptions("outbound", 2, 501, 500)

    def bfs_action() -> Any:
        return graph_search(star, source_id="s", options=search_options)

    def bfs_check(result: Any) -> None:
        if (result.stop_reason, result.discovered_nodes, result.examined_edges) != ("completed", 501, 500):
            raise AssertionError("BFS result differs")

    def path_action() -> tuple[int, str, int]:
        return _enumerate_parallel(parallel)

    def path_check(result: tuple[int, str, int]) -> None:
        if result != (62_750, "completed", 62_750):
            raise AssertionError("Path enumeration differs")

    vault_star = _vault_request(star=True)
    vault_parallel = _vault_request(star=False)
    adapter = VaultGraphProjectionAdapter()
    legacy = RustworkxGraphProjection()
    star_expected = legacy.project(vault_star)
    parallel_expected = legacy.project(vault_parallel)
    if adapter.project(vault_star) != star_expected or adapter.project(vault_parallel) != parallel_expected:
        raise AssertionError("Vault projection adapter differs from legacy projection")

    documents = _documents()
    with tempfile.TemporaryDirectory(prefix="graph-modules-bench-") as directory:
        root = Path(directory)
        write_results = _document_writes(root, documents, write_samples)
        write_peaks = _document_write_peaks(root, documents)
        read_path = root / "reads.sqlite"
        with _new_store(read_path) as store:
            store.update_documents(documents, collection_id="bench", expected_revision=0)

            def selected_action() -> Any:
                return store.read(collection_id="bench", selection=(documents[0].document_id,), limits=READ_LIMITS)

            def full_action() -> Any:
                return store.read(collection_id="bench", selection="all", limits=READ_LIMITS)

            full = full_action()
            _assert_document_graph(full, selected=False)

            def bundle_action() -> Any:
                return prepare_search(full, graph_limits=SEARCH_LIMITS)

            def bundle_check(bundle: Any) -> None:
                if bundle.read.digest != full.digest or len(bundle.read.edges) != 2000:
                    raise AssertionError("Search bundle differs")
                source = full.nodes[0].node_id
                result = graph_search(bundle.graph, source_id=source, options=SearchOptions("outbound", 0, 1, 0))
                if result.discovered_nodes != 1:
                    raise AssertionError("Search graph is unusable")

            def selected_bridge_evidence_action() -> tuple[Any, Any, Any]:
                read = selected_action()
                bundle = prepare_search(read, graph_limits=SEARCH_LIMITS)
                evidence = read.evidence_for(
                    node_ids=tuple(node.node_id for node in read.nodes),
                    edge_ids=tuple(edge.edge_id for edge in read.edges),
                )
                return read, bundle, evidence

            def selected_bridge_evidence_check(result: tuple[Any, Any, Any]) -> None:
                read, bundle, evidence = result
                _assert_document_graph(read, selected=True)
                if bundle.read is not read or evidence.unknown_node_ids or evidence.unknown_edge_ids:
                    raise AssertionError("Selected search bridge or evidence differs")
                found = sum(len(values) for _, values in (*evidence.by_node_id, *evidence.by_edge_id))
                if found != 5:
                    raise AssertionError("Selected evidence count differs")

            document_reads = {
                "selected_read_one_document": _samples(
                    selected_action,
                    lambda read: _assert_document_graph(read, selected=True),
                    count=read_samples,
                    warmups=warmups,
                ),
                "full_read": _samples(
                    full_action,
                    lambda read: _assert_document_graph(read, selected=False),
                    count=read_samples,
                    warmups=warmups,
                ),
                "prepare_search": _samples(
                    bundle_action,
                    bundle_check,
                    count=read_samples,
                    warmups=warmups,
                ),
                "selected_read_bridge_evidence": _samples(
                    selected_bridge_evidence_action,
                    selected_bridge_evidence_check,
                    count=read_samples,
                    warmups=warmups,
                ),
            }
            document_peaks = {
                "selected_read_one_document": _peak(
                    selected_action, lambda read: _assert_document_graph(read, selected=True)
                ),
                "full_read": _peak(full_action, lambda read: _assert_document_graph(read, selected=False)),
                "prepare_search": _peak(bundle_action, bundle_check),
                "selected_read_bridge_evidence": _peak(selected_bridge_evidence_action, selected_bridge_evidence_check),
            }
        _assert_no_plaintext(read_path)

    def check_star(result: Any) -> None:
        if result != star_expected:
            raise AssertionError("Vault star projection differs")

    def check_parallel(result: Any) -> None:
        if result != parallel_expected:
            raise AssertionError("Vault parallel projection differs")

    search_actions: dict[str, tuple[Callable[[], Any], Callable[[Any], None]]] = {
        "pure_bfs_500_star_edges": (bfs_action, bfs_check),
        "pure_paths_250_plus_250_parallel_edges": (path_action, path_check),
        "vault_adapter_500_star_edges": (
            lambda: adapter.project(vault_star),
            check_star,
        ),
        "legacy_500_star_edges": (
            lambda: legacy.project(vault_star),
            check_star,
        ),
        "vault_adapter_250_plus_250_parallel_edges": (
            lambda: adapter.project(vault_parallel),
            check_parallel,
        ),
    }
    search_results = {
        name: _samples(action, check, count=read_samples, warmups=warmups)
        for name, (action, check) in search_actions.items()
    }
    search_peaks = {name: _peak(action, check) for name, (action, check) in search_actions.items()}
    return {
        "environment": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "logical_cpu_count": os.cpu_count(),
            "python": sys.version.split()[0],
            "rustworkx": importlib.metadata.version("rustworkx"),
            "read_search_samples": read_samples,
            "fresh_write_samples": write_samples,
            "warmups": warmups,
            "latency_unit": "milliseconds",
            "memory_unit": "peak_tracemalloc_bytes",
            "percentile_method": "linear_interpolation",
            "latency_scope": "operation calls only; construction and self-checks excluded",
            "tracemalloc_scope": "separate operation run; Python allocations, not process RSS",
        },
        "workloads": {
            "pure_search_star": {"nodes": 501, "edges": 500, "max_depth": 2},
            "parallel_paths": {"nodes": 3, "edges": 500, "path_count": 62_750, "max_depth": 2},
            "vault_projection_star": {"nodes": 501, "edges": 500, "result_limit": 50},
            "vault_projection_parallel": {"nodes": 3, "edges": 500, "result_limit": 50},
            "document_graph": {
                "documents": 1000,
                "text_chars_each": 4096,
                "shared_tags": 2,
                "expected_nodes": 1002,
                "expected_edges": 2000,
                "expected_evidence": 5000,
            },
        },
        "latency": {**search_results, **document_reads, **write_results},
        "peak_tracemalloc_bytes": {**search_peaks, **document_peaks, **write_peaks},
        "self_checks": {
            "legacy_vault_projection_parity": True,
            "document_counts": True,
            "document_plaintext_absent_from_db": True,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--read-samples", type=int, default=20)
    parser.add_argument("--write-samples", type=int, default=5)
    parser.add_argument("--warmups", type=int, default=3)
    args = parser.parse_args()
    if args.read_samples < 20 or args.write_samples < 5 or args.warmups < 0:
        parser.error("Require at least 20 read/search samples, 5 fresh write samples, and nonnegative warmups")
    print(
        json.dumps(
            measure(read_samples=args.read_samples, write_samples=args.write_samples, warmups=args.warmups),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )


if __name__ == "__main__":
    main()
