"""Path-limited metadata apply for the session start refresh (re-audit 발견8).

``MetadataIndexer.apply_paths`` reads only the listed files, so its cost follows the number of
changed files and not the Vault size. Its result for those files must match a whole-Vault apply.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

from vault_graph.indexing.index_service import IndexService
from vault_graph.indexing.ingestion.vault_loader import VaultLoader
from vault_graph.indexing.metadata_indexer import MetadataIndexer
from vault_graph.operation.scope.vault_catalog import QueryScope, VaultCatalog, VaultCatalogEntry
from vault_graph.storage.interfaces.vector_store import VectorStore
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore


def write(root: Path, relative: str, body: str) -> None:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    root = tmp_path / "vault"
    for index in range(5):
        write(root, f"wiki/notes/note-{index}.md", f"---\ntitle: Note {index}\n---\n# Note {index}\nBody {index}\n")
    return root


def catalog_for(root: Path) -> VaultCatalog:
    return VaultCatalog.from_entries(
        entries=[VaultCatalogEntry.from_root(vault_id="main", root_path=root)], active_vault_id="main"
    )


def indexed_store(tmp_path: Path, root: Path, name: str) -> tuple[SQLiteMetadataStore, MetadataIndexer]:
    catalog = catalog_for(root)
    store = SQLiteMetadataStore(tmp_path / name / "metadata.sqlite3", initialize=True)
    indexer = MetadataIndexer(catalog=catalog, metadata_store=store)
    indexer.apply(scope=catalog.default_scope())
    return store, indexer


def rows(store: SQLiteMetadataStore) -> tuple[object, ...]:
    """Documents and chunks without the per-run revision and time columns."""
    with store.connect_for_tests() as connection:
        documents = connection.execute(
            "SELECT vault_id, path, document_id, content_hash, raw_sha256, provenance_family_id, is_tombstoned "
            "FROM documents ORDER BY vault_id, path"
        ).fetchall()
        chunks = connection.execute(
            "SELECT vault_id, chunk_id, path, content_hash FROM chunks ORDER BY vault_id, chunk_id"
        ).fetchall()
        keyword = connection.execute("SELECT vault_id, chunk_id, path FROM keyword_rows ORDER BY chunk_id").fetchall()
    return tuple(tuple(row) for row in documents), tuple(tuple(row) for row in chunks), tuple(map(tuple, keyword))


def test_apply_paths_matches_a_whole_vault_apply_for_new_changed_and_deleted_files(tmp_path: Path, vault: Path) -> None:
    partial, partial_indexer = indexed_store(tmp_path, vault, "partial")
    whole, whole_indexer = indexed_store(tmp_path, vault, "whole")
    write(vault, "wiki/notes/new.md", "# New\nFresh body\n")
    write(vault, "wiki/notes/note-1.md", "# Note 1\nChanged body\n")
    (vault / "wiki" / "notes" / "note-2.md").unlink()
    scope = catalog_for(vault).default_scope()

    plan = partial_indexer.apply_paths(
        scope=scope,
        changed_paths=(("main", "wiki/notes/new.md"), ("main", "wiki/notes/note-1.md")),
        deleted_paths=(("main", "wiki/notes/note-2.md"),),
    )
    whole_indexer.apply(scope=scope)

    assert plan.changed_paths == (("main", "wiki/notes/new.md"), ("main", "wiki/notes/note-1.md"))
    assert plan.deleted_paths == (("main", "wiki/notes/note-2.md"),)
    assert plan.vault_ids == ("main",)
    assert rows(partial) == rows(whole)


def test_apply_paths_reads_only_the_listed_files(tmp_path: Path, vault: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, indexer = indexed_store(tmp_path, vault, "state")
    write(vault, "wiki/notes/new.md", "# New\nFresh body\n")
    read: list[str] = []
    original = Path.read_bytes

    def tracking(self: Path) -> bytes:
        read.append(self.name)
        return original(self)

    def no_walk(*args: object, **kwargs: object) -> None:
        raise AssertionError("a path-limited apply must not walk the Vault")

    monkeypatch.setattr(Path, "read_bytes", tracking)
    monkeypatch.setattr(VaultLoader, "load_documents", no_walk)

    indexer.apply_paths(
        scope=catalog_for(vault).default_scope(), changed_paths=(("main", "wiki/notes/new.md"),), deleted_paths=()
    )

    assert read == ["new.md"]


def test_listed_file_that_is_gone_or_unchanged_is_handled(tmp_path: Path, vault: Path) -> None:
    store, indexer = indexed_store(tmp_path, vault, "state")
    (vault / "wiki" / "notes" / "note-3.md").unlink()

    plan = indexer.apply_paths(
        scope=catalog_for(vault).default_scope(),
        changed_paths=(("main", "wiki/notes/note-3.md"), ("main", "wiki/notes/note-4.md")),
        deleted_paths=(("main", "wiki/notes/never-indexed.md"),),
    )

    assert plan.changed_paths == ()
    assert plan.unchanged_paths == (("main", "wiki/notes/note-4.md"),)
    assert plan.deleted_paths == (("main", "wiki/notes/note-3.md"),)
    assert store.document_state("main", "wiki/notes/note-3.md").is_tombstoned is True


def test_paths_outside_the_scope_are_ignored(tmp_path: Path, vault: Path) -> None:
    store, indexer = indexed_store(tmp_path, vault, "state")
    write(vault, "outside/page.md", "# Outside\n")

    plan = indexer.apply_paths(
        scope=catalog_for(vault).default_scope(),
        changed_paths=(("main", "outside/page.md"), ("other", "wiki/notes/note-1.md")),
        deleted_paths=(("other", "wiki/notes/note-1.md"),),
    )

    assert plan.changed_paths == ()
    assert plan.deleted_paths == ()
    assert store.document_state("main", "outside/page.md").document_id is None


def test_index_service_run_apply_paths_writes_metadata_only_for_listed_paths(tmp_path: Path, vault: Path) -> None:
    catalog = catalog_for(vault)
    store, _ = indexed_store(tmp_path, vault, "state")
    write(vault, "wiki/notes/new.md", "# New\nFresh body\n")
    write(vault, "wiki/notes/unlisted.md", "# Unlisted\n")

    report = IndexService(catalog=catalog, metadata_store=store).run_apply_paths(
        scope=catalog.default_scope(), changed_paths=(("main", "wiki/notes/new.md"),), deleted_paths=()
    )

    assert report.exit_code == 0
    assert report.metadata.changed_paths == (("main", "wiki/notes/new.md"),)
    assert report.vector is None
    assert report.graph is None
    assert store.document_state("main", "wiki/notes/new.md").document_id is not None
    assert store.document_state("main", "wiki/notes/unlisted.md").document_id is None


# 발견13: a changed file and the pages it links by provenance stay in one family ---------------


def family(store: SQLiteMetadataStore, path: str) -> str | None:
    return store.document_state("main", path).provenance_family_id


def test_a_new_page_that_supersedes_an_unlisted_page_joins_its_family(tmp_path: Path, vault: Path) -> None:
    partial, partial_indexer = indexed_store(tmp_path, vault, "partial")
    whole, whole_indexer = indexed_store(tmp_path, vault, "whole")
    # "a-new" sorts before "note-4", so the family seed moves to the new page.
    write(vault, "wiki/notes/a-new.md", "---\ntitle: New\nsupersedes:\n  - wiki/notes/note-4.md\n---\n# New\nBody\n")
    scope = catalog_for(vault).default_scope()

    plan = partial_indexer.apply_paths(scope=scope, changed_paths=(("main", "wiki/notes/a-new.md"),), deleted_paths=())
    whole_indexer.apply(scope=scope)

    assert family(partial, "wiki/notes/a-new.md") == family(partial, "wiki/notes/note-4.md")
    assert plan.changed_paths == (("main", "wiki/notes/a-new.md"), ("main", "wiki/notes/note-4.md"))
    assert rows(partial) == rows(whole)


def test_a_changed_page_keeps_the_family_of_an_unlisted_page_that_points_to_it(tmp_path: Path, vault: Path) -> None:
    write(vault, "wiki/notes/a-old.md", "---\ntitle: Old\nsupersedes: [wiki/notes/note-3.md]\n---\n# Old\nBody\n")
    partial, partial_indexer = indexed_store(tmp_path, vault, "partial")
    whole, whole_indexer = indexed_store(tmp_path, vault, "whole")
    write(vault, "wiki/notes/note-3.md", "---\ntitle: Note 3\n---\n# Note 3\nChanged body\n")
    scope = catalog_for(vault).default_scope()

    partial_indexer.apply_paths(scope=scope, changed_paths=(("main", "wiki/notes/note-3.md"),), deleted_paths=())
    whole_indexer.apply(scope=scope)

    assert family(partial, "wiki/notes/note-3.md") == family(partial, "wiki/notes/a-old.md")
    assert rows(partial) == rows(whole)


# 정리 발견2: the index service, not the session start composition, drops vectors of removed chunks


class RecordingVectorStore:
    """Manifest of every chunk the store was given. Records the tombstones it is asked to apply."""

    def __init__(self, rows: tuple[object, ...]) -> None:
        self.rows = rows
        self.tombstones: list[tuple[str, str]] = []
        self.closed = False

    def export_manifest(self, scope: object) -> tuple[object, ...]:
        return self.rows

    def apply_vector_revision(
        self, *, vector_index_revision: str, records: tuple[object, ...], tombstones: tuple[Any, ...]
    ) -> None:
        assert records == ()
        self.tombstones.extend((item.vault_id, item.chunk_id) for item in tombstones)

    def close(self) -> None:
        self.closed = True


def _manifest(store: SQLiteMetadataStore) -> tuple[object, ...]:
    from types import SimpleNamespace

    from vault_graph.storage.interfaces.text_embeddings import EmbeddingModelSpec

    spec = EmbeddingModelSpec(model_name="m", model_version="v1", dimensions=4, spec_version="s1")
    scope = catalog_for_store_scope()
    return tuple(
        SimpleNamespace(
            vector_id=f"v-{chunk.chunk_id}", vault_id=chunk.vault_id, chunk_id=chunk.chunk_id, embedding_spec=spec
        )
        for chunk in store.list_chunks(scope)
    )


def catalog_for_store_scope() -> QueryScope:
    return QueryScope(vault_ids=("main",), content_scopes=("wiki",))


def test_run_apply_paths_drops_vectors_of_chunks_the_changed_files_lost(tmp_path: Path, vault: Path) -> None:
    catalog = catalog_for(vault)
    store, _ = indexed_store(tmp_path, vault, "state")
    vectors = RecordingVectorStore(_manifest(store))
    before = {
        chunk.chunk_id for chunk in store.list_chunks(catalog.default_scope()) if chunk.path.endswith("note-1.md")
    }
    write(vault, "wiki/notes/note-1.md", "# Note 1\nA different body\n")
    (vault / "wiki" / "notes" / "note-2.md").unlink()
    gone = {chunk.chunk_id for chunk in store.list_chunks(catalog.default_scope()) if chunk.path.endswith("note-2.md")}

    report = IndexService(catalog=catalog, metadata_store=store).run_apply_paths(
        scope=catalog.default_scope(),
        changed_paths=(("main", "wiki/notes/note-1.md"),),
        deleted_paths=(("main", "wiki/notes/note-2.md"),),
        open_vector_store=lambda: cast(VectorStore, vectors),
    )

    after = {chunk.chunk_id for chunk in store.list_chunks(catalog.default_scope())}
    assert report.exit_code == 0
    assert {chunk_id for _, chunk_id in vectors.tombstones} == (before | gone) - after
    assert vectors.tombstones
    assert vectors.closed


def test_run_apply_paths_opens_no_vector_store_when_no_chunk_was_removed(tmp_path: Path, vault: Path) -> None:
    catalog = catalog_for(vault)
    store, _ = indexed_store(tmp_path, vault, "state")
    write(vault, "wiki/notes/new.md", "# New\nFresh body\n")

    def never() -> None:
        raise AssertionError("a new file removes no chunk, so the vector store stays closed")

    IndexService(catalog=catalog, metadata_store=store).run_apply_paths(
        scope=catalog.default_scope(),
        changed_paths=(("main", "wiki/notes/new.md"),),
        deleted_paths=(),
        open_vector_store=never,
    )


def test_session_start_refresh_reads_no_store_itself() -> None:
    source = (
        Path(__file__).resolve().parents[1] / "src/vault_graph/interface/composition/recall_index_refresh.py"
    ).read_text(encoding="utf-8")

    for call in (
        ".list_document_states(",
        ".list_document_chunks(",
        ".document_state(",
        "export_manifest(",
        "apply_vector_revision(",
    ):
        assert call not in source
