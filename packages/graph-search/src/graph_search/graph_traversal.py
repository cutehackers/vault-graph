"""Bounded deterministic breadth-first traversal."""

from collections import deque
from dataclasses import dataclass

from graph_search.errors import GraphSearchError, InvalidSearchError, UnknownNodeError
from graph_search.graph_snapshot import GraphSnapshot, NodeId
from graph_search.search_results import Direction, SearchResult, Visit


def _valid_int(value: object, minimum: int) -> bool:
    return type(value) is int and value >= minimum


def _validate_direction(direction: object) -> bool:
    return type(direction) is str and direction in ("outbound", "inbound", "both")


@dataclass(frozen=True, slots=True)
class SearchOptions:
    direction: Direction
    max_depth: int
    max_nodes: int
    max_edge_examinations: int


def _validate_source(graph: GraphSnapshot, source_id: NodeId) -> None:
    if type(graph) is not GraphSnapshot:
        raise InvalidSearchError("Expected a GraphSnapshot.")
    if type(source_id) is not str or not graph._has_node(source_id):
        raise UnknownNodeError("Source node is not registered.")


def graph_search(graph: GraphSnapshot, *, source_id: NodeId, options: SearchOptions) -> SearchResult:
    """Return representative shortest paths within the requested work bounds."""
    if not isinstance(options, SearchOptions) or not (
        _validate_direction(options.direction)
        and _valid_int(options.max_depth, 0)
        and _valid_int(options.max_nodes, 1)
        and _valid_int(options.max_edge_examinations, 0)
    ):
        raise InvalidSearchError("Invalid search options.")
    _validate_source(graph, source_id)
    try:
        visits = [Visit(source_id, 0, None, None, None)]
        seen = {source_id}
        pending = deque([(source_id, 0)])
        examined = 0
        while pending:
            node_id, depth = pending.popleft()
            if depth == options.max_depth:
                continue
            for candidate in graph._candidates(node_id, options.direction):
                if examined == options.max_edge_examinations:
                    return SearchResult(
                        source_id,
                        options.direction,
                        options.max_depth,
                        tuple(visits),
                        "edge_limit",
                        examined,
                        len(visits),
                    )
                examined += 1
                if candidate.next_node_id in seen:
                    continue
                if len(visits) == options.max_nodes:
                    return SearchResult(
                        source_id,
                        options.direction,
                        options.max_depth,
                        tuple(visits),
                        "node_limit",
                        examined,
                        len(visits),
                    )
                seen.add(candidate.next_node_id)
                visits.append(Visit(candidate.next_node_id, depth + 1, node_id, candidate.edge_id, candidate.reversed))
                pending.append((candidate.next_node_id, depth + 1))
        return SearchResult(
            source_id, options.direction, options.max_depth, tuple(visits), "completed", examined, len(visits)
        )
    except GraphSearchError:
        raise
    except Exception as exc:
        raise GraphSearchError("Graph traversal failed.") from exc
