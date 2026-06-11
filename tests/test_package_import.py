from vault_graph import __version__
from vault_graph.retrieval import GraphCandidateResult, GraphSearchCandidateProvider, RetrievalCandidate


def test_package_exposes_version() -> None:
    assert __version__ == "0.1.0"


def test_retrieval_package_exports_graph_search_candidate_contracts() -> None:
    assert GraphCandidateResult.__name__ == "GraphCandidateResult"
    assert GraphSearchCandidateProvider.__name__ == "GraphSearchCandidateProvider"
    assert RetrievalCandidate.__name__ == "RetrievalCandidate"
