from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable

import rustworkx as rx

from vault_graph.projection.graph_projection import (
    GRAPH_PROJECTION_VERSION,
    GraphPath,
    GraphProjectionEdge,
    GraphProjectionInput,
    GraphProjectionNode,
    GraphProjectionResult,
)

STATUS_WEIGHTS = {
    "stated": 1.0,
    "inferred": 0.75,
    "contested": 0.45,
    "deprecated": 0.0,
}
DEPTH_WEIGHTS = {
    1: 1.0,
    2: 0.6,
}
RELATIONSHIP_TYPE_PRIORITY = (
    "supersedes",
    "depends_on",
    "blocks",
    "implements",
    "related_to",
    "mentions",
)


class RustworkxGraphProjection:
    def project(self, request: GraphProjectionInput) -> GraphProjectionResult:
        graph = rx.PyDiGraph(multigraph=True)
        nodes = _dedupe_nodes(request.nodes)
        node_index_by_identity: dict[tuple[str, str], int] = {}
        for node in sorted(nodes, key=_node_sort_key):
            node_index_by_identity[(node.vault_id, node.entity_id)] = graph.add_node(node)

        filtered_relationships = tuple(
            edge
            for edge in sorted(request.relationships, key=_edge_sort_key)
            if _edge_allowed(edge=edge, request=request)
            and (edge.source_vault_id, edge.source_entity_id) in node_index_by_identity
            and (edge.target_vault_id, edge.target_entity_id) in node_index_by_identity
        )
        working_edges = filtered_relationships[: request.edge_limit]
        edge_limit_truncated = len(filtered_relationships) > len(working_edges)
        for edge in working_edges:
            graph.add_edge(
                node_index_by_identity[(edge.source_vault_id, edge.source_entity_id)],
                node_index_by_identity[(edge.target_vault_id, edge.target_entity_id)],
                edge,
            )

        paths = tuple(
            sorted(
                _enumerate_paths(
                    request=request,
                    graph=graph,
                    node_index_by_identity=node_index_by_identity,
                    nodes=nodes,
                ),
                key=_path_sort_key,
            )
        )
        limited_paths = paths[: request.limit]
        return GraphProjectionResult(
            projection_build_id=_projection_build_id(request=request, nodes=nodes),
            graph_projection_version=GRAPH_PROJECTION_VERSION,
            source_graph_revisions=tuple(sorted(request.source_graph_revisions)),
            node_count=len(nodes),
            edge_count=len(working_edges),
            truncated=edge_limit_truncated or len(paths) > len(limited_paths),
            paths=limited_paths,
        )


def _dedupe_nodes(nodes: tuple[GraphProjectionNode, ...]) -> tuple[GraphProjectionNode, ...]:
    nodes_by_identity: dict[tuple[str, str], GraphProjectionNode] = {}
    for node in nodes:
        nodes_by_identity.setdefault((node.vault_id, node.entity_id), node)
    return tuple(nodes_by_identity.values())


def _enumerate_paths(
    *,
    request: GraphProjectionInput,
    graph: rx.PyDiGraph,
    node_index_by_identity: dict[tuple[str, str], int],
    nodes: tuple[GraphProjectionNode, ...],
) -> Iterable[GraphPath]:
    node_by_identity = {(node.vault_id, node.entity_id): node for node in nodes}
    identity_by_node_index = {node_index: identity for identity, node_index in node_index_by_identity.items()}

    seed_keys = {(seed.vault_id, seed.entity_id) for seed in request.seeds}
    seen_paths: set[tuple[tuple[str, str], tuple[str, str], tuple[str, ...]]] = set()
    for seed in sorted(request.seeds, key=_node_sort_key):
        seed_key = (seed.vault_id, seed.entity_id)
        seed_index = node_index_by_identity[seed_key]
        for target_key, path_edges in _walk_paths(
            graph=graph,
            identity_by_node_index=identity_by_node_index,
            current_index=seed_index,
            visited_keys=(seed_key,),
            path_edges=(),
            max_depth=request.max_depth,
            direction=request.direction,
        ):
            if target_key in seed_keys:
                continue
            path_key = (seed_key, target_key, tuple(edge.relationship_id for edge in path_edges))
            if path_key in seen_paths:
                continue
            seen_paths.add(path_key)
            target = node_by_identity[target_key]
            yield GraphPath(
                seed=seed,
                target=target,
                edges=path_edges,
                depth=len(path_edges),
                score=_score_path(path_edges),
                explanation=_explain_path(path_edges),
            )


def _walk_paths(
    *,
    graph: rx.PyDiGraph,
    identity_by_node_index: dict[int, tuple[str, str]],
    current_index: int,
    visited_keys: tuple[tuple[str, str], ...],
    path_edges: tuple[GraphProjectionEdge, ...],
    max_depth: int,
    direction: str,
) -> Iterable[tuple[tuple[str, str], tuple[GraphProjectionEdge, ...]]]:
    if len(path_edges) >= max_depth:
        return
    for next_index, edge in _adjacent_edges(graph=graph, node_index=current_index, direction=direction):
        next_key = identity_by_node_index[next_index]
        if next_key in visited_keys:
            continue
        next_path_edges = (*path_edges, edge)
        yield next_key, next_path_edges
        yield from _walk_paths(
            graph=graph,
            identity_by_node_index=identity_by_node_index,
            current_index=next_index,
            visited_keys=(*visited_keys, next_key),
            path_edges=next_path_edges,
            max_depth=max_depth,
            direction=direction,
        )


def _adjacent_edges(
    *,
    graph: rx.PyDiGraph,
    node_index: int,
    direction: str,
) -> tuple[tuple[int, GraphProjectionEdge], ...]:
    adjacent: list[tuple[int, GraphProjectionEdge]] = []
    if direction in ("out", "both"):
        adjacent.extend((int(target_index), edge) for _, target_index, edge in graph.out_edges(node_index))
    if direction in ("in", "both"):
        adjacent.extend((int(source_index), edge) for source_index, _, edge in graph.in_edges(node_index))
    return tuple(sorted(adjacent, key=lambda item: (_edge_sort_key(item[1]), item[0])))


def _edge_allowed(*, edge: GraphProjectionEdge, request: GraphProjectionInput) -> bool:
    if request.relationship_types and edge.relationship_type not in request.relationship_types:
        return False
    if edge.status not in request.statuses:
        return False
    if not request.include_cross_vault and edge.source_vault_id != edge.target_vault_id:
        return False
    return True


def _score_path(edges: tuple[GraphProjectionEdge, ...]) -> float:
    if not edges:
        return 0.0
    depth_weight = DEPTH_WEIGHTS.get(len(edges), 0.0)
    weighted_confidences = tuple(edge.confidence * STATUS_WEIGHTS.get(edge.status, 0.0) for edge in edges)
    return min(weighted_confidences) * depth_weight


def _explain_path(edges: tuple[GraphProjectionEdge, ...]) -> str:
    relationship_types = " -> ".join(edge.relationship_type for edge in edges)
    return f"{len(edges)}-edge graph path via {relationship_types}"


def _projection_build_id(*, request: GraphProjectionInput, nodes: tuple[GraphProjectionNode, ...]) -> str:
    payload = {
        "version": GRAPH_PROJECTION_VERSION,
        "actual_scope_keys": sorted(request.actual_scope_keys),
        "seed_identities": sorted((seed.vault_id, seed.entity_id) for seed in request.seeds),
        "working_node_identities": sorted((node.vault_id, node.entity_id) for node in nodes),
        "source_graph_revisions": sorted(request.source_graph_revisions),
        "max_depth": request.max_depth,
        "direction": request.direction,
        "relationship_types": sorted(request.relationship_types),
        "statuses": sorted(request.statuses),
        "include_cross_vault": request.include_cross_vault,
        "limit": request.limit,
        "edge_limit": request.edge_limit,
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _node_sort_key(node: GraphProjectionNode) -> tuple[str, str, str]:
    return (node.vault_id, node.normalized_name, node.entity_id)


def _edge_sort_key(edge: GraphProjectionEdge) -> tuple[str, str, str, str, str]:
    return (
        edge.source_vault_id,
        edge.target_vault_id,
        edge.relationship_type,
        edge.relationship_id,
        edge.target_entity_id,
    )


def _path_sort_key(path: GraphPath) -> tuple[float, int, int, str, str, str, str]:
    first_edge = path.edges[0]
    return (
        -path.score,
        path.depth,
        _relationship_type_rank(first_edge.relationship_type),
        first_edge.relationship_type,
        path.target.vault_id,
        path.target.normalized_name,
        first_edge.relationship_id,
    )


def _relationship_type_rank(relationship_type: str) -> int:
    try:
        return RELATIONSHIP_TYPE_PRIORITY.index(relationship_type)
    except ValueError:
        return len(RELATIONSHIP_TYPE_PRIORITY)
