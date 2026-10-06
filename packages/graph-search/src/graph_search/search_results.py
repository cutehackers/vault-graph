"""Immutable traversal results and lazy representative path reconstruction."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Literal

from graph_search.graph_snapshot import EdgeId, NodeId

type Direction = Literal["outbound", "inbound", "both"]
type SearchStopReason = Literal["completed", "node_limit", "edge_limit"]
type PathStopReason = Literal["completed", "path_limit", "edge_limit", "cancelled", "failed"]


@dataclass(frozen=True, slots=True)
class TraversalStep:
    edge_id: EdgeId
    from_id: NodeId
    to_id: NodeId
    reversed: bool


@dataclass(frozen=True, slots=True)
class Path:
    node_ids: tuple[NodeId, ...]
    steps: tuple[TraversalStep, ...]


@dataclass(frozen=True, slots=True)
class Visit:
    node_id: NodeId
    depth: int
    parent_id: NodeId | None
    parent_edge_id: EdgeId | None
    reversed: bool | None


@dataclass(frozen=True, slots=True)
class PathLookup:
    status: Literal["found", "not_observed"]
    path: Path | None


@dataclass(frozen=True, slots=True)
class SearchResult:
    source_id: NodeId
    direction: Direction
    max_depth: int
    visits: tuple[Visit, ...]
    stop_reason: SearchStopReason
    examined_edges: int
    discovered_nodes: int
    _visit_by_id: Mapping[NodeId, Visit] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_visit_by_id", MappingProxyType({visit.node_id: visit for visit in self.visits}))

    def path_to(self, target_id: NodeId) -> PathLookup:
        if type(target_id) is not str:
            return PathLookup("not_observed", None)
        if target_id not in self._visit_by_id:
            return PathLookup("not_observed", None)
        node_ids: list[str] = []
        steps: list[TraversalStep] = []
        current_id = target_id
        while True:
            visit = self._visit_by_id[current_id]
            node_ids.append(current_id)
            if visit.parent_id is None:
                break
            assert visit.parent_edge_id is not None and visit.reversed is not None
            steps.append(TraversalStep(visit.parent_edge_id, visit.parent_id, current_id, visit.reversed))
            current_id = visit.parent_id
        return PathLookup("found", Path(tuple(reversed(node_ids)), tuple(reversed(steps))))


@dataclass(frozen=True, slots=True)
class PathSummary:
    stop_reason: PathStopReason
    emitted_paths: int
    examined_edges: int
