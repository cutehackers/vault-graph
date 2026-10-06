from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError
from itertools import permutations
from tracemalloc import get_traced_memory, start, stop
from unittest.mock import patch

import networkx as nx
import pytest

from graph_search import (
    Edge,
    GraphCapacityError,
    GraphLimits,
    GraphSearchError,
    GraphSnapshot,
    InvalidGraphError,
    InvalidSearchError,
    PathOptions,
    SearchOptions,
    UnknownNodeError,
    graph_search,
    search_paths,
)


def graph() -> GraphSnapshot:
    return GraphSnapshot.build(
        node_ids=("C", "A", "B"),
        edges=(Edge("bc", "B", "C"), Edge("ab", "A", "B")),
        limits=GraphLimits(3, 2, 16, 64),
    )


def test_public_search_and_path_iteration() -> None:
    snapshot = graph()
    result = graph_search(snapshot, source_id="A", options=SearchOptions("outbound", 2, 3, 2))
    assert result.stop_reason == "completed"
    assert [(visit.node_id, visit.depth) for visit in result.visits] == [("A", 0), ("B", 1), ("C", 2)]
    path = result.path_to("C").path
    assert path is not None and path.node_ids == ("A", "B", "C")
    with search_paths(snapshot, source_id="A", options=PathOptions("outbound", 2, 2, 2)) as paths:
        assert [path.node_ids for path in paths] == [("A", "B"), ("A", "B", "C")]
    assert paths.summary is not None and paths.summary.stop_reason == "completed"


def make_graph(nodes: tuple[str, ...], edges: tuple[Edge, ...]) -> GraphSnapshot:
    return GraphSnapshot.build(
        node_ids=nodes,
        edges=edges,
        limits=GraphLimits(max(1, len(nodes)), max(1, len(edges)), 32, 1024),
    )


@pytest.mark.parametrize(
    ("nodes", "edges", "error"),
    [
        (["A"], (), InvalidGraphError),
        (("A", "A"), (), InvalidGraphError),
        (("",), (), InvalidGraphError),
        ((" ",), (), InvalidGraphError),
        (("\ud800",), (), InvalidGraphError),
        (("A",), (Edge("e", "A", "B"),), InvalidGraphError),
        (("A",), (Edge("e", "A", "A"), Edge("e", "A", "A")), InvalidGraphError),
        (("A",), (Edge(1, "A", "A"),), InvalidGraphError),  # type: ignore[arg-type]
    ],
)
def test_graph_rejects_invalid_input(nodes: object, edges: object, error: type[Exception]) -> None:
    with pytest.raises(error):
        GraphSnapshot.build(node_ids=nodes, edges=edges, limits=GraphLimits(3, 3, 32, 128))  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("nodes", "edges", "limits"),
    [
        (("A", "B"), (), GraphLimits(1, 1, 8, 32)),
        (("A",), (Edge("e1", "A", "A"), Edge("e2", "A", "A")), GraphLimits(1, 1, 8, 32)),
        (("한글",), (), GraphLimits(1, 1, 5, 32)),
        (("A",), (Edge("e", "A", "A"),), GraphLimits(1, 1, 8, 3)),
    ],
)
def test_graph_capacity(nodes: tuple[str, ...], edges: tuple[Edge, ...], limits: GraphLimits) -> None:
    with pytest.raises(GraphCapacityError):
        GraphSnapshot.build(node_ids=nodes, edges=edges, limits=limits)


def test_bfs_matches_independent_networkx_distances() -> None:
    edges = (Edge("ab", "A", "B"), Edge("ac", "A", "C"), Edge("bd", "B", "D"), Edge("cd", "C", "D"))
    snapshot = make_graph(("D", "C", "A", "B", "isolated"), edges)
    nx_graph: nx.DiGraph[str] = nx.DiGraph()
    nx_graph.add_nodes_from(("D", "C", "A", "B", "isolated"))
    nx_graph.add_edges_from((edge.source_id, edge.target_id) for edge in edges)
    expected = nx.single_source_shortest_path_length(nx_graph, "A", cutoff=2)
    result = graph_search(snapshot, source_id="A", options=SearchOptions("outbound", 2, 5, 10))
    assert {visit.node_id: visit.depth for visit in result.visits} == expected
    assert [visit.node_id for visit in result.visits] == ["A", "B", "C", "D"]
    path = result.path_to("D").path
    assert path is not None and path.steps[0].edge_id == "ab"
    assert result.path_to("isolated").status == "not_observed"


def test_direction_parallel_edges_and_self_loop() -> None:
    snapshot = make_graph(("A", "B"), (Edge("z", "A", "B"), Edge("a", "A", "B"), Edge("loop", "A", "A")))
    result = graph_search(snapshot, source_id="B", options=SearchOptions("inbound", 1, 2, 2))
    path = result.path_to("A").path
    assert path is not None and path.steps[0].edge_id == "a"
    assert path.steps[0].reversed is True
    with search_paths(snapshot, source_id="A", options=PathOptions("both", 1, 3, 4)) as paths:
        found = list(paths)
    assert [(path.steps[0].edge_id, path.steps[0].reversed) for path in found] == [("a", False), ("z", False)]
    assert paths.summary is not None and paths.summary.examined_edges == 3


def test_bfs_limits_check_next_work_not_equal_count() -> None:
    snapshot = make_graph(("A", "B", "C"), (Edge("ab", "A", "B"), Edge("bc", "B", "C")))
    assert graph_search(snapshot, source_id="A", options=SearchOptions("outbound", 0, 1, 0)).stop_reason == "completed"
    assert graph_search(snapshot, source_id="A", options=SearchOptions("outbound", 1, 2, 1)).stop_reason == "completed"
    limited = graph_search(snapshot, source_id="A", options=SearchOptions("outbound", 2, 2, 2))
    assert (limited.stop_reason, limited.examined_edges, limited.discovered_nodes) == ("node_limit", 2, 2)
    assert limited.path_to("C").status == "not_observed"
    assert graph_search(snapshot, source_id="A", options=SearchOptions("outbound", 2, 3, 1)).stop_reason == "edge_limit"
    assert graph_search(snapshot, source_id="C", options=SearchOptions("outbound", 2, 1, 0)).stop_reason == "completed"


def test_paths_cycle_and_exact_limit_complete() -> None:
    snapshot = make_graph(("A", "B"), (Edge("ab", "A", "B"), Edge("ba", "B", "A")))
    with search_paths(snapshot, source_id="A", options=PathOptions("outbound", 2, 1, 2)) as paths:
        assert [path.node_ids for path in paths] == [("A", "B")]
    assert paths.summary is not None
    assert (paths.summary.stop_reason, paths.summary.emitted_paths, paths.summary.examined_edges) == ("completed", 1, 2)
    with search_paths(snapshot, source_id="A", options=PathOptions("outbound", 2, 1, 1)) as paths:
        assert [path.node_ids for path in paths] == [("A", "B")]
    assert paths.summary is not None and paths.summary.stop_reason == "edge_limit"


def test_paths_limit_after_next_valid_path() -> None:
    snapshot = make_graph(("A", "B", "C"), (Edge("ab", "A", "B"), Edge("ac", "A", "C")))
    with search_paths(snapshot, source_id="A", options=PathOptions("outbound", 1, 1, 2)) as paths:
        assert [path.node_ids for path in paths] == [("A", "B")]
    assert paths.summary is not None
    assert (paths.summary.stop_reason, paths.summary.examined_edges) == ("path_limit", 2)


def test_path_iterator_pause_cancel_and_errors() -> None:
    snapshot = graph()
    with search_paths(snapshot, source_id="A", options=PathOptions("outbound", 2, 2, 2)) as resumable:
        for path in resumable:
            assert path.node_ids == ("A", "B")
            break
        assert resumable.summary is None
        assert next(resumable).node_ids == ("A", "B", "C")
        with pytest.raises(StopIteration):
            next(resumable)
    assert resumable.summary is not None and resumable.summary.stop_reason == "completed"
    with search_paths(snapshot, source_id="A", options=PathOptions("outbound", 2, 2, 2)) as paths:
        assert next(paths).node_ids == ("A", "B")
        assert paths.summary is None
        assert next(paths).node_ids == ("A", "B", "C")
    assert paths.summary is not None and paths.summary.stop_reason == "cancelled"
    with pytest.raises(StopIteration):
        next(paths)
    paths.close()
    assert paths.summary is not None and paths.summary.stop_reason == "cancelled"
    with pytest.raises(AttributeError):
        paths.summary = None
    with pytest.raises(UnknownNodeError):
        search_paths(snapshot, source_id="missing", options=PathOptions("outbound", 1, 1, 1))
    with pytest.raises(InvalidSearchError):
        graph_search(snapshot, source_id="A", options=SearchOptions("outbound", 1, True, 1))
    with pytest.raises(InvalidSearchError):
        search_paths(snapshot, source_id="A", options=PathOptions("sideways", 1, 1, 1))


def test_permutations_concurrency_and_result_immutability() -> None:
    edges = (Edge("ab", "A", "B"), Edge("ac", "A", "C"), Edge("bd", "B", "D"))
    expected = graph_search(
        make_graph(("A", "B", "C", "D"), edges), source_id="A", options=SearchOptions("outbound", 2, 4, 8)
    )
    for order in permutations(edges):
        snapshot = make_graph(("D", "C", "B", "A"), order)
        assert graph_search(snapshot, source_id="A", options=SearchOptions("outbound", 2, 4, 8)) == expected
    snapshot = make_graph(("A", "B", "C", "D"), edges)
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert all(
            result == expected
            for result in pool.map(
                lambda _: graph_search(snapshot, source_id="A", options=SearchOptions("outbound", 2, 4, 8)),
                range(64),
            )
        )
    with pytest.raises(FrozenInstanceError):
        expected.visits[0].depth = 3  # type: ignore[misc]
    with pytest.raises(AttributeError):
        snapshot._nodes = frozenset()


def test_all_simple_paths_match_independent_edge_oracle() -> None:
    edges = (
        Edge("ab1", "A", "B"),
        Edge("ab2", "A", "B"),
        Edge("ac", "A", "C"),
        Edge("bc", "B", "C"),
        Edge("ca", "C", "A"),
        Edge("loop", "A", "A"),
    )
    snapshot = make_graph(("A", "B", "C"), edges)

    def oracle(current: str, visited: frozenset[str], path: tuple[str, ...]) -> list[tuple[str, ...]]:
        if len(path) == 2:
            return []
        found: list[tuple[str, ...]] = []
        for edge in edges:
            if edge.source_id == current and edge.target_id not in visited:
                extended = (*path, edge.id)
                found.append(extended)
                found.extend(oracle(edge.target_id, visited | {edge.target_id}, extended))
        return found

    expected = oracle("A", frozenset({"A"}), ())
    with search_paths(snapshot, source_id="A", options=PathOptions("outbound", 2, 20, 100)) as paths:
        observed = [tuple(step.edge_id for step in path.steps) for path in paths]
    assert set(observed) == set(expected)
    assert paths.summary is not None and paths.summary.stop_reason == "completed"


def test_failed_iterator_is_terminal_and_keeps_cause() -> None:
    snapshot = graph()
    paths = search_paths(snapshot, source_id="A", options=PathOptions("outbound", 2, 2, 2))
    with patch.object(GraphSnapshot, "_candidates", side_effect=RuntimeError("broken backend")):
        with pytest.raises(GraphSearchError) as error:
            next(paths)
    assert isinstance(error.value.__cause__, RuntimeError)
    assert paths.summary is not None and paths.summary.stop_reason == "failed"
    with pytest.raises(StopIteration):
        next(paths)


def test_no_external_io_during_build_and_search() -> None:
    with (
        patch("builtins.open", side_effect=AssertionError("file access")),
        patch("socket.socket", side_effect=AssertionError("socket access")),
        patch("subprocess.Popen", side_effect=AssertionError("process access")),
    ):
        snapshot = graph()
        graph_search(snapshot, source_id="A", options=SearchOptions("outbound", 2, 3, 2))
        with search_paths(snapshot, source_id="A", options=PathOptions("outbound", 2, 2, 2)) as paths:
            assert len(list(paths)) == 2


def test_large_path_space_stays_streaming() -> None:
    nodes = ("s",) + tuple(f"{level}-{side}" for level in range(20) for side in "ab")
    edges = tuple(
        Edge(f"{level}-{left}-{right}", f"{level}-{left}", f"{level + 1}-{right}")
        for level in range(19)
        for left in "ab"
        for right in "ab"
    ) + (Edge("start-a", "s", "0-a"), Edge("start-b", "s", "0-b"))
    snapshot = GraphSnapshot.build(
        node_ids=nodes,
        edges=edges,
        limits=GraphLimits(len(nodes), len(edges), 32, 4096),
    )
    start()
    try:
        with search_paths(snapshot, source_id="s", options=PathOptions("outbound", 20, 1, 100)) as paths:
            assert len(next(paths).steps) == 1
            assert paths.summary is None
            assert list(paths) == []
        _, peak_bytes = get_traced_memory()
    finally:
        stop()
    assert paths.summary is not None and paths.summary.stop_reason == "path_limit"
    assert peak_bytes < 2_000_000
