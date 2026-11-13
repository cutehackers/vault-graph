"""Spec 2026-11-11 §4.2.6: stale counts and store revisions are computed again only when the store files change."""

from __future__ import annotations

from collections.abc import Hashable
from pathlib import Path

from tests.fakes.deterministic_text_embeddings import DeterministicTextEmbeddings
from tests.fakes.in_memory_vector_store import InMemoryVectorStore
from tests.test_app_search_readiness_service import HealthyKeywordIndex, metadata_store_with_chunk
from tests.test_search_readiness_vector_stale_counter import FixedStaleCounter
from tests.test_vector_indexer import SPEC
from vault_graph.operation.readiness.search_readiness_service import ReadOnlySearchReadiness, sqlite_files_signature
from vault_graph.operation.scope.vault_catalog import QueryScope


def _readiness(
    tmp_path: Path, counter: FixedStaleCounter, signature: list[Hashable] | None
) -> tuple[ReadOnlySearchReadiness, QueryScope]:
    metadata_store, scope = metadata_store_with_chunk(tmp_path)
    readiness = ReadOnlySearchReadiness(
        metadata_store=metadata_store,
        keyword_index=HealthyKeywordIndex(),
        vector_store=InMemoryVectorStore(),
        text_embeddings=DeterministicTextEmbeddings(SPEC),
        vector_stale_counter=counter,
        store_signature=None if signature is None else (lambda: signature[0]),
    )
    return readiness, scope


def test_unchanged_signature_reuses_stale_count(tmp_path: Path) -> None:
    counter = FixedStaleCounter(2)
    signature: list[Hashable] = [("unchanged", str(tmp_path))]
    readiness, scope = _readiness(tmp_path, counter, signature)

    first = readiness.check(actual_scopes=(scope,))
    second = readiness.check(actual_scopes=(scope,))

    assert counter.scopes == [scope]
    assert first.scope_readiness == second.scope_readiness
    assert first.store_revisions == second.store_revisions


def test_changed_signature_counts_again(tmp_path: Path) -> None:
    counter = FixedStaleCounter(2)
    signature: list[Hashable] = [("before", str(tmp_path))]
    readiness, scope = _readiness(tmp_path, counter, signature)
    readiness.check(actual_scopes=(scope,))

    signature[0] = ("after", str(tmp_path))
    counter.count = 5
    report = readiness.check(actual_scopes=(scope,))

    assert counter.scopes == [scope, scope]
    assert report.vector_stale_count == 5


def test_without_signature_counts_on_every_check(tmp_path: Path) -> None:
    counter = FixedStaleCounter(2)
    readiness, scope = _readiness(tmp_path, counter, None)

    readiness.check(actual_scopes=(scope,))
    readiness.check(actual_scopes=(scope,))

    assert counter.scopes == [scope, scope]


def test_signature_changes_when_the_file_or_its_wal_changes(tmp_path: Path) -> None:
    database = tmp_path / "store.sqlite3"
    database.write_bytes(b"one")
    first = sqlite_files_signature((database,))

    (tmp_path / "store.sqlite3-wal").write_bytes(b"wal")
    second = sqlite_files_signature((database,))
    database.write_bytes(b"one two")
    third = sqlite_files_signature((database,))

    assert len({first, second, third}) == 3
    assert sqlite_files_signature((database,)) == third
