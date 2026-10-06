from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .errors import MissingSearchDependencyError
from .querying import DocumentGraphSnapshot

if TYPE_CHECKING:
    from graph_search import GraphLimits, GraphSnapshot


@dataclass(frozen=True, slots=True)
class SearchBundle:
    graph: GraphSnapshot
    read: DocumentGraphSnapshot


def prepare_search(read: DocumentGraphSnapshot, *, graph_limits: GraphLimits) -> SearchBundle:
    try:
        from graph_search import Edge, GraphSnapshot
    except ImportError as exc:
        raise MissingSearchDependencyError("Install nolemy-graph-document[search]") from exc
    graph = GraphSnapshot.build(
        node_ids=tuple(node.node_id for node in read.nodes),
        edges=tuple(
            Edge(edge.edge_id, edge.source_node_id, edge.target_node_id) for edge in read.edges
        ),
        limits=graph_limits,
    )
    return SearchBundle(graph, read)
