from pathlib import Path


def test_retrieval_package_does_not_import_indexing_or_local_status_store() -> None:
    retrieval_files = Path("src/vault_graph/retrieval").glob("*.py")
    combined = "\n".join(path.read_text(encoding="utf-8") for path in retrieval_files)

    assert "vault_graph.app" not in combined
    assert "vault_graph.indexing" not in combined
    assert "vector_status_store" not in combined
    assert "ReadOnlySearchReadiness" not in combined
