import pytest

from vault_graph.errors import KeywordIndexError
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.storage.interfaces.keyword_index import KeywordHit, KeywordQuery


def test_keyword_query_rejects_empty_text() -> None:
    with pytest.raises(KeywordIndexError, match="query_text is required"):
        KeywordQuery(query_text="  ", scope=QueryScope(vault_ids=("default",)), limit=10)


def test_keyword_query_rejects_non_positive_limit() -> None:
    with pytest.raises(KeywordIndexError, match="limit must be positive"):
        KeywordQuery(query_text="GraphRAG", scope=QueryScope(vault_ids=("default",)), limit=0)


def test_keyword_hit_requires_vault_scoped_identity() -> None:
    hit = KeywordHit(
        vault_id="default",
        document_id="default:wiki/page.md",
        chunk_id="chunk-1",
        rank=1,
        score=-1.25,
        backend="sqlite-fts5",
        index_revision="metadata-1",
        matched_fields=("text", "section"),
    )

    assert hit.vault_id == "default"
    assert hit.chunk_id == "chunk-1"
    assert hit.rank == 1
    assert hit.score == -1.25
    assert hit.matched_fields == ("text", "section")


def test_keyword_hit_rejects_unranked_candidate() -> None:
    with pytest.raises(KeywordIndexError, match="rank must be positive"):
        KeywordHit(
            vault_id="default",
            document_id="doc",
            chunk_id="chunk",
            rank=0,
            score=0.0,
            backend="sqlite-fts5",
            index_revision="metadata-1",
            matched_fields=("text",),
        )
