"""Streaming depth-first node-simple path traversal."""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Self

from graph_search.errors import GraphSearchError, InvalidSearchError
from graph_search.graph_snapshot import GraphSnapshot, NodeId, _Candidate
from graph_search.graph_traversal import _valid_int, _validate_direction, _validate_source
from graph_search.search_results import Direction, Path, PathStopReason, PathSummary, TraversalStep


@dataclass(frozen=True, slots=True)
class PathOptions:
    direction: Direction
    max_depth: int
    max_paths: int
    max_edge_examinations: int


class PathTraversal(Iterator[Path]):
    """One-shot iterator with explicit terminal summary and cancellation."""

    __slots__ = (
        "_graph",
        "_source_id",
        "_options",
        "_frames",
        "_nodes",
        "_steps",
        "_seen",
        "_emitted",
        "_examined",
        "_summary",
    )

    def __init__(self, graph: GraphSnapshot, *, source_id: NodeId, options: PathOptions) -> None:
        if not isinstance(options, PathOptions) or not (
            _validate_direction(options.direction)
            and _valid_int(options.max_depth, 0)
            and _valid_int(options.max_paths, 1)
            and _valid_int(options.max_edge_examinations, 0)
        ):
            raise InvalidSearchError("Invalid path options.")
        _validate_source(graph, source_id)
        self._graph = graph
        self._source_id = source_id
        self._options = options
        self._frames: list[tuple[tuple[_Candidate, ...], int]] = []
        self._nodes = [source_id]
        self._steps: list[TraversalStep] = []
        self._seen = {source_id}
        self._emitted = 0
        self._examined = 0
        self._summary: PathSummary | None = None

    @property
    def summary(self) -> PathSummary | None:
        return self._summary

    def __iter__(self) -> Self:
        return self

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def close(self) -> None:
        if self.summary is None:
            self._finish("cancelled")

    def _finish(self, reason: PathStopReason) -> None:
        self._summary = PathSummary(reason, self._emitted, self._examined)
        self._frames.clear()
        self._nodes.clear()
        self._steps.clear()
        self._seen.clear()

    def __next__(self) -> Path:
        if self.summary is not None:
            raise StopIteration
        try:
            if not self._frames:
                if self._options.max_depth == 0:
                    self._finish("completed")
                    raise StopIteration
                self._frames.append((self._graph._candidates(self._source_id, self._options.direction), 0))
            while self._frames:
                candidates, cursor = self._frames[-1]
                if cursor == len(candidates):
                    self._frames.pop()
                    if self._frames:
                        self._seen.remove(self._nodes.pop())
                        self._steps.pop()
                    continue
                if self._examined == self._options.max_edge_examinations:
                    self._finish("edge_limit")
                    raise StopIteration
                candidate = candidates[cursor]
                self._frames[-1] = (candidates, cursor + 1)
                self._examined += 1
                if candidate.next_node_id in self._seen:
                    continue
                if self._emitted == self._options.max_paths:
                    self._finish("path_limit")
                    raise StopIteration
                from_id = self._nodes[-1]
                self._nodes.append(candidate.next_node_id)
                self._steps.append(
                    TraversalStep(candidate.edge_id, from_id, candidate.next_node_id, candidate.reversed)
                )
                self._seen.add(candidate.next_node_id)
                path = Path(tuple(self._nodes), tuple(self._steps))
                self._emitted += 1
                if len(self._steps) < self._options.max_depth:
                    self._frames.append((self._graph._candidates(candidate.next_node_id, self._options.direction), 0))
                else:
                    self._seen.remove(self._nodes.pop())
                    self._steps.pop()
                return path
            self._finish("completed")
            raise StopIteration
        except StopIteration:
            raise
        except Exception as exc:
            self._finish("failed")
            raise GraphSearchError("Path traversal failed.") from exc


def search_paths(graph: GraphSnapshot, *, source_id: NodeId, options: PathOptions) -> PathTraversal:
    """Enumerate bounded non-empty node-simple paths in deterministic DFS order."""
    return PathTraversal(graph, source_id=source_id, options=options)
