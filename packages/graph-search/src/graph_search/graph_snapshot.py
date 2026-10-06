"""Validated immutable graph snapshot and deterministic adjacency."""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

import rustworkx as rx

from graph_search.errors import GraphCapacityError, InvalidGraphError

type NodeId = str
type EdgeId = str


@dataclass(frozen=True, slots=True)
class Edge:
    id: EdgeId
    source_id: NodeId
    target_id: NodeId


@dataclass(frozen=True, slots=True)
class GraphLimits:
    max_nodes: int
    max_edges: int
    max_id_bytes: int
    max_total_id_bytes: int


@dataclass(frozen=True, slots=True)
class _Candidate:
    next_node_id: NodeId
    edge_id: EdgeId
    reversed: bool


def _positive_int(value: object) -> bool:
    return type(value) is int and value >= 1


def _id_bytes(value: object) -> int:
    if type(value) is not str or not value or not value.strip():
        raise InvalidGraphError("Graph IDs must be non-empty strings.")
    try:
        return len(value.encode("utf-8"))
    except UnicodeError as exc:
        raise InvalidGraphError("Graph IDs must be UTF-8 encodable.") from exc


class GraphSnapshot:
    """A read-only copy of a bounded directed multigraph."""

    __slots__ = ("_nodes", "_outbound", "_inbound", "_both", "_native")
    _nodes: frozenset[NodeId]
    _outbound: Mapping[NodeId, tuple[_Candidate, ...]]
    _inbound: Mapping[NodeId, tuple[_Candidate, ...]]
    _both: Mapping[NodeId, tuple[_Candidate, ...]]
    _native: rx.PyDiGraph

    def __init__(self) -> None:
        raise TypeError("Use GraphSnapshot.build().")

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("GraphSnapshot is immutable.")

    @classmethod
    def build(cls, *, node_ids: tuple[NodeId, ...], edges: tuple[Edge, ...], limits: GraphLimits) -> "GraphSnapshot":
        if not isinstance(limits, GraphLimits) or not all(
            _positive_int(getattr(limits, name))
            for name in ("max_nodes", "max_edges", "max_id_bytes", "max_total_id_bytes")
        ):
            raise InvalidGraphError("Graph limits must be positive integers.")
        if type(node_ids) is not tuple or type(edges) is not tuple:
            raise InvalidGraphError("Nodes and edges must be tuples.")
        if len(node_ids) > limits.max_nodes or len(edges) > limits.max_edges:
            raise GraphCapacityError("Graph node or edge capacity exceeded.")

        total_bytes = 0

        def count_id(value: object) -> None:
            nonlocal total_bytes
            size = _id_bytes(value)
            if size > limits.max_id_bytes:
                raise GraphCapacityError("Graph ID byte capacity exceeded.")
            total_bytes += size
            if total_bytes > limits.max_total_id_bytes:
                raise GraphCapacityError("Graph total ID byte capacity exceeded.")

        for node_id in node_ids:
            count_id(node_id)
        if len(set(node_ids)) != len(node_ids):
            raise InvalidGraphError("Duplicate node ID.")
        nodes = frozenset(node_ids)
        edge_ids: set[str] = set()
        for edge in edges:
            if type(edge) is not Edge:
                raise InvalidGraphError("Edges must be Edge values.")
            for value in (edge.id, edge.source_id, edge.target_id):
                count_id(value)
            if edge.id in edge_ids:
                raise InvalidGraphError("Duplicate edge ID.")
            edge_ids.add(edge.id)
            if edge.source_id not in nodes or edge.target_id not in nodes:
                raise InvalidGraphError("Edge endpoint is not registered.")

        ordered_nodes = sorted(nodes)
        ordered_edges = sorted(edges, key=lambda edge: edge.id)
        native = rx.PyDiGraph(multigraph=True)
        native_indices = {node_id: native.add_node(node_id) for node_id in ordered_nodes}
        outbound: dict[str, list[_Candidate]] = {node_id: [] for node_id in ordered_nodes}
        inbound: dict[str, list[_Candidate]] = {node_id: [] for node_id in ordered_nodes}
        both: dict[str, list[_Candidate]] = {node_id: [] for node_id in ordered_nodes}
        for edge in ordered_edges:
            native.add_edge(native_indices[edge.source_id], native_indices[edge.target_id], edge.id)
            forward = _Candidate(edge.target_id, edge.id, False)
            outbound[edge.source_id].append(forward)
            both[edge.source_id].append(forward)
            reverse = _Candidate(edge.source_id, edge.id, True)
            inbound[edge.target_id].append(reverse)
            if edge.source_id != edge.target_id:
                both[edge.target_id].append(reverse)

        instance = object.__new__(cls)
        object.__setattr__(instance, "_nodes", nodes)

        def key(candidate: _Candidate) -> tuple[str, str, bool]:
            return candidate.next_node_id, candidate.edge_id, candidate.reversed

        object.__setattr__(
            instance,
            "_outbound",
            MappingProxyType({node: tuple(sorted(items, key=key)) for node, items in outbound.items()}),
        )
        object.__setattr__(
            instance,
            "_inbound",
            MappingProxyType({node: tuple(sorted(items, key=key)) for node, items in inbound.items()}),
        )
        object.__setattr__(
            instance, "_both", MappingProxyType({node: tuple(sorted(items, key=key)) for node, items in both.items()})
        )
        object.__setattr__(instance, "_native", native)
        return instance

    def _candidates(self, node_id: NodeId, direction: str) -> tuple[_Candidate, ...]:
        if direction == "outbound":
            return self._outbound[node_id]
        if direction == "inbound":
            return self._inbound[node_id]
        return self._both[node_id]

    def _has_node(self, node_id: NodeId) -> bool:
        return node_id in self._nodes
