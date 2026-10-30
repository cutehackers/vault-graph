from pathlib import Path

from tests.fakes.deterministic_text_embeddings import DeterministicTextEmbeddings
from tests.fakes.in_memory_vector_store import InMemoryVectorStore
from tests.test_app_search_readiness_service import HealthyKeywordIndex, metadata_store_with_chunk
from tests.test_vector_indexer import SPEC
from vault_graph.interface.composition.read_only_service_factory import VectorIndexerStaleCounter
from vault_graph.operation.readiness.search_readiness_service import ReadOnlySearchReadiness
from vault_graph.operation.scope.vault_catalog import QueryScope


class FixedStaleCounter:
    def __init__(self, count: int | None) -> None:
        self.count = count
        self.scopes: list[QueryScope] = []

    def stale_count(self, *, scope: QueryScope) -> int | None:
        self.scopes.append(scope)
        return self.count


def test_readiness_uses_injected_stale_counter(tmp_path: Path) -> None:
    metadata_store, scope = metadata_store_with_chunk(tmp_path)
    counter = FixedStaleCounter(3)
    readiness = ReadOnlySearchReadiness(
        metadata_store=metadata_store,
        keyword_index=HealthyKeywordIndex(),
        vector_store=InMemoryVectorStore(),
        text_embeddings=DeterministicTextEmbeddings(SPEC),
        vector_stale_counter=counter,
    )

    report = readiness.check(actual_scopes=(scope,))

    assert counter.scopes == [scope]
    assert report.vector_stale_count == 3
    assert report.scope_readiness[0].vector_stale_count == 3


def test_readiness_without_stale_counter_reports_unknown_staleness(tmp_path: Path) -> None:
    metadata_store, scope = metadata_store_with_chunk(tmp_path)
    readiness = ReadOnlySearchReadiness(
        metadata_store=metadata_store,
        keyword_index=HealthyKeywordIndex(),
        vector_store=InMemoryVectorStore(),
        text_embeddings=DeterministicTextEmbeddings(SPEC),
    )

    report = readiness.check(actual_scopes=(scope,))

    assert report.vector_stale_count is None
    assert report.scope_readiness[0].vector_stale_count is None


def test_vector_indexer_stale_counter_counts_pending_upserts(tmp_path: Path) -> None:
    metadata_store, scope = metadata_store_with_chunk(tmp_path)
    counter = VectorIndexerStaleCounter(
        metadata_store=metadata_store,
        vector_store=InMemoryVectorStore(),
        text_embeddings=DeterministicTextEmbeddings(SPEC),
    )

    assert counter.stale_count(scope=scope) == 1
