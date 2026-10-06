# nolemy-graph-search

Deterministic, bounded traversal over a caller-supplied directed multigraph. The
snapshot is read-only and independent of any storage or application domain.

```python
from graph_search import Edge, GraphLimits, GraphSnapshot, SearchOptions, graph_search

graph = GraphSnapshot.build(
    node_ids=("A", "B"),
    edges=(Edge("e1", "A", "B"),),
    limits=GraphLimits(2, 1, 32, 128),
)
result = graph_search(graph, source_id="A", options=SearchOptions("outbound", 1, 2, 1))
assert result.path_to("B").path.node_ids == ("A", "B")
```

Always inspect `stop_reason` or a path traversal's `summary` before treating
unobserved nodes or paths as absent. A depth bound or work limit can leave
results incomplete. Callers choose finite capacity and work limits.
