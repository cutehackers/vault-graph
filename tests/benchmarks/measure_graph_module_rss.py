"""Measure process RSS and durable document DB size on fixed graph-module inputs.

Run with ``uv run --python 3.12 python tests/benchmarks/measure_graph_module_rss.py``.
Each stage runs in a fresh process. RSS is absolute process high-water, including
imports and fixture setup; it is not the incremental cost of an operation.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import platform
import resource
import subprocess
import sys
import tempfile
import time
import tomllib
from pathlib import Path
from typing import Any

import measure_graph_modules as fixture  # type: ignore[import-not-found]
from graph_document import GraphDocument
from graph_document.search_bridge import prepare_search
from graph_search import PathOptions, SearchOptions, graph_search, search_paths

from vault_graph.projection.rustworkx_projection import RustworkxGraphProjection
from vault_graph.projection.vault_graph_projection_adapter import VaultGraphProjectionAdapter

RSS_LIMIT_BYTES = 512 * 1024 * 1024
DOCUMENT_DB_LIMIT_BYTES = 64 * 1024 * 1024
REPORT_PATH = Path("docs/design/reports/2026-10-04-graph-module-rss.json")
STAGES = (
    "search_prepare",
    "search_bfs",
    "search_path_restore",
    "search_paths",
    "projection_adapter_star",
    "projection_adapter_parallel",
    "document_initial_write",
    "document_full_read",
    "document_selected_read",
    "document_bridge",
    "document_restore",
)


def _max_rss_bytes() -> int:
    measured = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return measured if sys.platform == "darwin" else measured * 1024


def _local_distribution_version(module_name: str, project_file: Path) -> dict[str, str]:
    candidates = importlib.metadata.packages_distributions().get(module_name)
    if candidates:
        name = candidates[0]
    else:
        with project_file.open("rb") as stream:
            name = tomllib.load(stream)["project"]["name"]
    return {"distribution": name, "version": importlib.metadata.version(name)}


def _db_sizes(path: Path) -> dict[str, int]:
    return {
        name: candidate.stat().st_size if candidate.is_file() else 0
        for name, candidate in (
            ("db", path),
            ("wal", Path(f"{path}-wal")),
            ("shm", Path(f"{path}-shm")),
        )
    }


def _check_projection(*, star: bool) -> None:
    request = fixture._vault_request(star=star)
    actual = VaultGraphProjectionAdapter().project(request)
    expected = RustworkxGraphProjection().project(request)
    if actual != expected:
        raise AssertionError("Vault projection adapter differs from legacy projection")


def _write_document_fixture(path: Path) -> None:
    documents = fixture._documents()
    with fixture._new_store(path) as store:
        result = store.update_documents(documents, collection_id="bench", expected_revision=0)
        if result.graph_revision != 1 or len(result.changed_document_ids) != fixture.DOCUMENT_COUNT:
            raise AssertionError("Initial document extraction differs")
    fixture._assert_no_plaintext(path)


def _document_stage(stage: str, root: Path) -> dict[str, Any]:
    path = root / "document.sqlite"
    _write_document_fixture(path)
    if stage != "document_initial_write":
        with GraphDocument.open(
            path, mode="read_only", limits=fixture.DOCUMENT_LIMITS, profile=fixture.PROFILE
        ) as store:
            if stage == "document_selected_read":
                read = store.read(collection_id="bench", selection=("doc0000",), limits=fixture.READ_LIMITS)
                fixture._assert_document_graph(read, selected=True)
            else:
                read = store.read(collection_id="bench", selection="all", limits=fixture.READ_LIMITS)
                fixture._assert_document_graph(read, selected=False)
                if stage == "document_bridge":
                    bundle = prepare_search(read, graph_limits=fixture.SEARCH_LIMITS)
                    if bundle.read.digest != read.digest or len(bundle.read.edges) != 2000:
                        raise AssertionError("Document search bridge differs")
                elif stage == "document_restore":
                    if read.graph_revision != 1 or len(read.documents) != fixture.DOCUMENT_COUNT:
                        raise AssertionError("Restored document graph differs")
    fixture._assert_no_plaintext(path)
    sizes = _db_sizes(path)
    return {"db_bytes": sizes, "durable_db_total_bytes": sum(sizes.values())}


def _run_stage(stage: str, root: Path) -> dict[str, Any]:
    started = time.perf_counter_ns()
    result: dict[str, Any] = {}
    if stage == "search_prepare":
        star = fixture._search_star()
        parallel = fixture._search_parallel()
        star_result = graph_search(star, source_id="s", options=SearchOptions("outbound", 1, 501, 500))
        parallel_result = graph_search(parallel, source_id="a", options=SearchOptions("outbound", 2, 3, 500))
        if (star_result.discovered_nodes, star_result.examined_edges, parallel_result.discovered_nodes) != (
            501,
            500,
            3,
        ):
            raise AssertionError("Search fixture shape differs")
    elif stage == "search_bfs":
        snapshot = fixture._search_star()
        search = graph_search(snapshot, source_id="s", options=SearchOptions("outbound", 2, 501, 500))
        if (search.stop_reason, search.discovered_nodes, search.examined_edges) != ("completed", 501, 500):
            raise AssertionError("BFS result differs")
    elif stage == "search_path_restore":
        parallel = fixture._search_parallel()
        parallel_result = graph_search(parallel, source_id="a", options=SearchOptions("outbound", 2, 3, 500))
        restored = parallel_result.path_to("c")
        if restored.status != "found" or restored.path is None:
            raise AssertionError("Parallel path was not restored")
        if restored.path.node_ids != ("a", "b", "c") or tuple(
            (step.edge_id, step.reversed) for step in restored.path.steps
        ) != (("ab000", False), ("bc000", False)):
            raise AssertionError("Parallel path steps differ")
        inbound = graph_search(parallel, source_id="c", options=SearchOptions("inbound", 2, 3, 500))
        reversed_path = inbound.path_to("a")
        if reversed_path.status != "found" or reversed_path.path is None:
            raise AssertionError("Reversed path was not restored")
        if reversed_path.path.node_ids != ("c", "b", "a") or tuple(
            (step.edge_id, step.reversed) for step in reversed_path.path.steps
        ) != (("bc000", True), ("ab000", True)):
            raise AssertionError("Reversed path steps differ")
        star = fixture._search_star()
        star_result = graph_search(star, source_id="s", options=SearchOptions("outbound", 1, 501, 500))
        for index in range(500):
            target = f"n{index:03d}"
            found = star_result.path_to(target)
            if found.status != "found" or found.path is None:
                raise AssertionError("Star path was not restored")
            if found.path.node_ids != ("s", target) or tuple(
                (step.edge_id, step.reversed) for step in found.path.steps
            ) != ((f"e{index:03d}", False),):
                raise AssertionError("Star path steps differ")
    elif stage == "search_paths":
        snapshot = fixture._search_parallel()
        with search_paths(snapshot, source_id="a", options=PathOptions("outbound", 2, 62_750, 62_750)) as paths:
            count = sum(1 for _ in paths)
        if paths.summary is None or (count, paths.summary.stop_reason, paths.summary.examined_edges) != (
            62_750,
            "completed",
            62_750,
        ):
            raise AssertionError("Path enumeration differs")
    elif stage == "projection_adapter_star":
        _check_projection(star=True)
    elif stage == "projection_adapter_parallel":
        _check_projection(star=False)
    elif stage.startswith("document_"):
        result.update(_document_stage(stage, root))
    else:
        raise ValueError(f"Unknown stage: {stage}")
    result.update(
        {
            "stage": stage,
            "elapsed_ms": round((time.perf_counter_ns() - started) / 1_000_000, 6),
            "max_rss_bytes": _max_rss_bytes(),
            "self_check": "passed",
        }
    )
    return result


def measure() -> dict[str, Any]:
    results: dict[str, dict[str, Any]] = {}
    repository = Path(__file__).resolve().parents[2]
    with tempfile.TemporaryDirectory(prefix="graph-module-rss-") as directory:
        root = Path(directory)
        for stage in STAGES:
            stage_root = root / stage
            stage_root.mkdir()
            completed = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), "--child", stage, "--root", str(stage_root)],
                capture_output=True,
                text=True,
                check=True,
            )
            results[stage] = json.loads(completed.stdout)
    failures = [
        f"{name}: RSS {value['max_rss_bytes']} > {RSS_LIMIT_BYTES}"
        for name, value in results.items()
        if value["max_rss_bytes"] > RSS_LIMIT_BYTES
    ]
    failures.extend(
        f"{name}: durable DB {value['durable_db_total_bytes']} > {DOCUMENT_DB_LIMIT_BYTES}"
        for name, value in results.items()
        if "durable_db_total_bytes" in value and value["durable_db_total_bytes"] > DOCUMENT_DB_LIMIT_BYTES
    )
    return {
        "environment": {
            "platform": platform.platform(),
            "python": sys.version.split()[0],
            "rss_unit": "bytes",
            "rss_scope": (
                "absolute process high-water including imports and fixture setup; each stage is a fresh process"
            ),
            "elapsed_scope": "child stage wall time including fixture setup and checks; excludes imports and startup",
            "elapsed_unit": "milliseconds",
            "db_size_scope": "SQLite DB plus WAL plus SHM after child process closes the store",
            "graph_search": _local_distribution_version(
                "graph_search", repository / "packages/graph-search/pyproject.toml"
            ),
            "graph_document": _local_distribution_version(
                "graph_document", repository / "packages/graph-document/pyproject.toml"
            ),
            "rustworkx": {
                "distribution": "rustworkx",
                "version": importlib.metadata.version("rustworkx"),
            },
        },
        "limits": {"max_rss_bytes": RSS_LIMIT_BYTES, "durable_document_db_bytes": DOCUMENT_DB_LIMIT_BYTES},
        "workloads": {
            "search_star": {"nodes": 501, "edges": 500},
            "search_paths": {"nodes": 3, "edges": 500, "paths": 62_750},
            "document_graph": {"documents": 1000, "text_chars_each": 4096, "shared_tags": 2},
        },
        "stages": results,
        "passed": not failures,
        "failures": failures,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--child", choices=STAGES)
    parser.add_argument("--root", type=Path)
    args = parser.parse_args()
    if args.child is not None:
        if args.root is None:
            parser.error("--child requires --root")
        print(json.dumps(_run_stage(args.child, args.root), sort_keys=True))
        return
    report = measure()
    path = REPORT_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{path}: {'passed' if report['passed'] else 'failed'}")
    for failure in report["failures"]:
        print(failure)
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
