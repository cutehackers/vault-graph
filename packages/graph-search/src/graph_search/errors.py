"""Public graph construction and traversal errors."""


class GraphSearchError(Exception):
    code = "graph_search_error"

    def __init__(self, message: str = "Graph search failed.") -> None:
        super().__init__(message)


class InvalidGraphError(GraphSearchError):
    code = "invalid_graph"


class GraphCapacityError(GraphSearchError):
    code = "graph_capacity"


class InvalidSearchError(GraphSearchError):
    code = "invalid_search"


class UnknownNodeError(GraphSearchError):
    code = "unknown_node"
