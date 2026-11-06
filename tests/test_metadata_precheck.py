"""Spec 2026-11-05 §4.3.3 사전 검사 (A-18): an incremental run reads only files whose size, mtime or
index code changed. Its result must equal a full run's.

위험B4 기록: `git checkout`과 Vault `sessions capture`는 파일을 새로 쓰므로 mtime이 바뀐다. 사전 검사가
놓치는 경우는 크기와 mtime을 함께 보존하는 복사(`cp -p`, `rsync -t`로 같은 크기 내용을 덮어씀)뿐이고,
`vg index --full`이 바로잡는다.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.test_metadata_indexer_paths import catalog_for, rows, write
from vault_graph.indexing import metadata_indexer
from vault_graph.indexing.ingestion.vault_loader import VaultLoader
from vault_graph.indexing.metadata_indexer import MetadataIndexer
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    root = tmp_path / "vault"
    for index in range(5):
        write(root, f"wiki/notes/note-{index}.md", f"---\ntitle: Note {index}\n---\n# Note {index}\nBody {index}\n")
    return root


@pytest.fixture
def reads(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Vault-relative paths the loader opened, in order."""
    opened: list[str] = []
    original = VaultLoader._load

    def spy(self: VaultLoader, entry: object, markdown_path: Path) -> object:
        opened.append(markdown_path.relative_to(entry.root_path).as_posix())  # type: ignore[attr-defined]
        return original(self, entry, markdown_path)  # type: ignore[arg-type]

    monkeypatch.setattr(VaultLoader, "_load", spy)
    return opened


def indexer_for(tmp_path: Path, root: Path, name: str = "store") -> tuple[SQLiteMetadataStore, MetadataIndexer]:
    catalog = catalog_for(root)
    store = SQLiteMetadataStore(tmp_path / name / "metadata.sqlite3", initialize=True)
    return store, MetadataIndexer(catalog=catalog, metadata_store=store)


def apply(indexer: MetadataIndexer, root: Path, *, full: bool = False) -> object:
    return indexer.apply(scope=catalog_for(root).default_scope(), full=full)


def full_rows(tmp_path: Path, root: Path) -> tuple[object, ...]:
    store, indexer = indexer_for(tmp_path, root, "full")
    apply(indexer, root, full=True)
    return rows(store)


def test_unchanged_files_are_not_opened(tmp_path: Path, vault: Path, reads: list[str]) -> None:
    store, indexer = indexer_for(tmp_path, vault)
    apply(indexer, vault)
    reads.clear()

    plan = apply(indexer, vault)

    assert reads == []
    assert plan.changed_paths == ()  # type: ignore[attr-defined]
    assert len(plan.unchanged_paths) == 5  # type: ignore[attr-defined]


def test_changed_size_is_read_and_reindexed(tmp_path: Path, vault: Path, reads: list[str]) -> None:
    store, indexer = indexer_for(tmp_path, vault)
    apply(indexer, vault)
    reads.clear()
    write(vault, "wiki/notes/note-1.md", "---\ntitle: Note 1\n---\n# Note 1\nA longer body now\n")

    plan = apply(indexer, vault)

    assert reads == ["wiki/notes/note-1.md"]
    assert plan.changed_paths == (("main", "wiki/notes/note-1.md"),)  # type: ignore[attr-defined]
    assert rows(store) == full_rows(tmp_path, vault)


def test_touched_file_is_read_once_then_skipped(tmp_path: Path, vault: Path, reads: list[str]) -> None:
    store, indexer = indexer_for(tmp_path, vault)
    apply(indexer, vault)
    path = vault / "wiki/notes/note-2.md"
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000_000))
    reads.clear()

    plan = apply(indexer, vault)
    assert reads == ["wiki/notes/note-2.md"]
    assert plan.changed_paths == ()  # type: ignore[attr-defined]

    reads.clear()
    apply(indexer, vault)
    assert reads == []


def test_full_run_reads_every_file(tmp_path: Path, vault: Path, reads: list[str]) -> None:
    store, indexer = indexer_for(tmp_path, vault)
    apply(indexer, vault)
    reads.clear()

    apply(indexer, vault, full=True)

    assert len(reads) == 5


def test_new_index_code_reads_every_file(
    tmp_path: Path, vault: Path, reads: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    store, indexer = indexer_for(tmp_path, vault)
    apply(indexer, vault)
    reads.clear()
    monkeypatch.setattr(metadata_indexer, "INDEX_CODE_PARTS", (*metadata_indexer.INDEX_CODE_PARTS, "next-chunker"))

    apply(indexer, vault)

    assert len(reads) == 5


def test_new_and_deleted_files_match_a_full_run(tmp_path: Path, vault: Path, reads: list[str]) -> None:
    store, indexer = indexer_for(tmp_path, vault)
    twin, twin_indexer = indexer_for(tmp_path, vault, "twin")
    apply(indexer, vault)
    apply(twin_indexer, vault)
    (vault / "wiki/notes/note-3.md").unlink()
    write(vault, "wiki/notes/new.md", "---\ntitle: New\n---\n# New\nNew body\n")
    reads.clear()

    plan = apply(indexer, vault)

    assert reads == ["wiki/notes/new.md"]
    assert plan.deleted_paths == (("main", "wiki/notes/note-3.md"),)  # type: ignore[attr-defined]
    apply(twin_indexer, vault, full=True)
    assert rows(store) == rows(twin)


def test_new_page_superseding_an_unread_page_joins_its_family(tmp_path: Path, vault: Path, reads: list[str]) -> None:
    store, indexer = indexer_for(tmp_path, vault)
    apply(indexer, vault)
    write(
        vault,
        "wiki/notes/note-0-v2.md",
        "---\ntitle: Note 0 v2\nsupersedes:\n  - wiki/notes/note-0.md\n---\n# Note 0 v2\nNewer body\n",
    )
    reads.clear()

    apply(indexer, vault)

    assert set(reads) == {"wiki/notes/note-0-v2.md", "wiki/notes/note-0.md"}
    assert rows(store) == full_rows(tmp_path, vault)


def test_store_without_recorded_stats_reads_every_file_once(tmp_path: Path, vault: Path, reads: list[str]) -> None:
    store, indexer = indexer_for(tmp_path, vault)
    apply(indexer, vault)
    with store.connect_for_tests() as connection:
        connection.execute("DROP TABLE document_source_stats")
    reads.clear()

    apply(indexer, vault)
    assert len(reads) == 5
    reads.clear()
    apply(indexer, vault)
    assert reads == []


def test_read_only_store_from_before_the_stats_table_reports_no_stats(tmp_path: Path, vault: Path) -> None:
    store, indexer = indexer_for(tmp_path, vault)
    apply(indexer, vault)
    with store.connect_for_tests() as connection:
        connection.execute("DROP TABLE document_source_stats")
    reader = SQLiteMetadataStore(tmp_path / "store" / "metadata.sqlite3", initialize=False)

    assert reader.list_source_stats(("main",)) == {}
