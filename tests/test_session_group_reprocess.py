"""Incremental runs reprocess a whole session group and a whole provenance family (spec 2026-11-05 §4.2.13, A-36).

Same Vault state, same result: the incremental run and a full run give the same chunk id set, keyword
rows and vector metadata. A group with no changed file is not opened.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fakes.deterministic_text_embeddings import DeterministicTextEmbeddings
from tests.fakes.in_memory_vector_store import InMemoryVectorStore
from tests.test_metadata_indexer_paths import catalog_for
from tests.test_session_v1_v2_overlap import (
    KEPT_V1_PART1_EXCHANGE,
    NOTE_PATH,
    OVERLAPPED_V1_EXCHANGES,
    SESSION,
    SESSION_DIR,
    V1_PART1_PATH,
    V1_PART2_PATH,
    V2_4444_PART1,
    V2_4444_PART3,
    V2_PART3_PATH,
    session_vault,
    v2_part3_text,
    write,
)
from vault_graph.indexing.ingestion.document_normalizer import ChunkSnapshot
from vault_graph.indexing.ingestion.session_exchange_v1_chunker import SESSION_EXCHANGE_V1_VERSION
from vault_graph.indexing.ingestion.session_exchange_v2_chunker import SESSION_EXCHANGE_V2_VERSION
from vault_graph.indexing.ingestion.vault_loader import VaultLoader
from vault_graph.indexing.metadata_indexer import MetadataIndexer
from vault_graph.indexing.revision_planner import MetadataRevisionPlan
from vault_graph.indexing.vector_index_adapter import VectorIndexer
from vault_graph.operation.scope.vault_catalog import QueryScope
from vault_graph.storage.interfaces.text_embeddings import EmbeddingModelSpec
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore

SPEC = EmbeddingModelSpec(model_name="deterministic", model_version="v1", dimensions=4, spec_version="spec-v1")


class Index:
    """One metadata store with its vector store, indexed together like `vg index`."""

    def __init__(self, tmp_path: Path, root: Path, name: str) -> None:
        self.root = root
        self.catalog = catalog_for(root)
        self.store = SQLiteMetadataStore(tmp_path / name / "metadata.sqlite3", initialize=True)
        self.metadata = MetadataIndexer(catalog=self.catalog, metadata_store=self.store)
        self.vectors = InMemoryVectorStore()
        self.vector_indexer = VectorIndexer(
            chunk_store=self.store, vector_store=self.vectors, text_embeddings=DeterministicTextEmbeddings(SPEC)
        )

    def run(self, *, full: bool = False) -> MetadataRevisionPlan:
        scope = self.catalog.default_scope()
        plan = self.metadata.apply(scope=scope, full=full)
        result = self.vector_indexer.apply(scopes=(scope,), full=full)
        assert result.failed is False, result.error
        return plan

    def result(self) -> tuple[object, ...]:
        """Chunk rows, keyword rows and vector metadata without per-run revision and time columns."""
        with self.store.connect_for_tests() as connection:
            documents = connection.execute(
                "SELECT vault_id, path, document_id, content_hash, provenance_family_id, is_tombstoned, "
                "session_group_key FROM documents WHERE is_tombstoned = 0 ORDER BY vault_id, path"
            ).fetchall()
            chunks = connection.execute(
                "SELECT vault_id, chunk_id, path, content_hash, provenance_family_id, parent_key, keyword_metadata, "
                "section_path_json, source_locators_json FROM chunks ORDER BY vault_id, chunk_id"
            ).fetchall()
            keyword = connection.execute(
                "SELECT r.vault_id, r.chunk_id, r.path, r.provenance_family_id, k.section, k.title, k.frontmatter, "
                "k.text FROM keyword_rows r JOIN keyword_chunks k ON k.rowid = r.rowid ORDER BY r.vault_id, r.chunk_id"
            ).fetchall()
        vectors = sorted(
            (
                row.vector_id,
                row.vault_id,
                row.document_id,
                row.chunk_id,
                row.content_scope,
                row.source_chunk_hash,
                row.chunker_version,
                row.source_role,
                row.provenance_family_id,
            )
            for row in self.vectors.export_manifest(self.catalog.default_scope())
        )
        return (
            tuple(map(tuple, documents)),
            tuple(map(tuple, chunks)),
            tuple(map(tuple, keyword)),
            tuple(vectors),
        )

    def parents(self, path: str) -> set[str]:
        with self.store.connect_for_tests() as connection:
            rows = connection.execute("SELECT parent_key FROM chunks WHERE path = ?", (path,)).fetchall()
        return {str(row[0]) for row in rows}


def full_result(tmp_path: Path, root: Path, name: str = "full") -> tuple[object, ...]:
    index = Index(tmp_path, root, name)
    index.run(full=True)
    return index.result()


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


def test_adding_v2_part_reprocesses_unchanged_v1_parts_and_matches_a_full_run(tmp_path: Path, reads: list[str]) -> None:
    root = session_vault(tmp_path / "vault", with_v2=False)
    index = Index(tmp_path, root, "incremental")
    index.run()
    assert OVERLAPPED_V1_EXCHANGES <= index.parents(V1_PART1_PATH)
    write(root, V2_PART3_PATH, v2_part3_text())
    reads.clear()

    plan = index.run()

    assert sorted(reads) == sorted([V1_PART1_PATH, V1_PART2_PATH, V2_PART3_PATH])
    assert ("main", V1_PART1_PATH) in plan.changed_paths
    assert ("main", V1_PART2_PATH) in plan.unchanged_paths
    assert index.parents(V1_PART1_PATH) == {KEPT_V1_PART1_EXCHANGE}
    assert index.result() == full_result(tmp_path, root)


def test_removing_v2_part_brings_back_the_v1_exchanges(tmp_path: Path) -> None:
    root = session_vault(tmp_path / "vault")
    index = Index(tmp_path, root, "incremental")
    index.run()
    assert index.parents(V1_PART1_PATH) == {KEPT_V1_PART1_EXCHANGE}
    (root / V2_PART3_PATH).unlink()

    plan = index.run()

    assert plan.deleted_paths == (("main", V2_PART3_PATH),)
    assert OVERLAPPED_V1_EXCHANGES <= index.parents(V1_PART1_PATH)
    assert index.result() == full_result(tmp_path, root)


def test_group_without_a_changed_file_is_not_opened(tmp_path: Path, reads: list[str]) -> None:
    root = session_vault(tmp_path / "vault")
    index = Index(tmp_path, root, "incremental")
    index.run()
    write(root, NOTE_PATH, "---\ntitle: Note\n---\n# Note\nChanged body\n")
    reads.clear()

    index.run()

    assert reads == [NOTE_PATH]
    reads.clear()
    index.run()
    assert reads == []


def test_duplicate_exchange_owner_moves_when_the_first_file_goes(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    first = f"{SESSION_DIR}/{V2_4444_PART1.name}"
    later = f"{SESSION_DIR}/{V2_4444_PART3.name}"
    write(root, later, V2_4444_PART3.read_text(encoding="utf-8"))
    index = Index(tmp_path, root, "incremental")
    index.run()
    session = "44444444-4444-4444-8444-444444444444"
    assert index.parents(later) == {f"{session}:u-410", f"{session}:u-420"}

    write(root, first, V2_4444_PART1.read_text(encoding="utf-8"))
    plan = index.run()
    assert index.parents(later) == set()
    assert any("session_exchange_duplicate" in warning for warning in plan.warnings)
    assert index.result() == full_result(tmp_path, root, "full-1")

    (root / first).unlink()
    index.run()
    assert index.parents(later) == {f"{session}:u-410", f"{session}:u-420"}
    assert index.result() == full_result(tmp_path, root, "full-2")


def test_session_group_key_is_stored_for_session_files_only(tmp_path: Path) -> None:
    root = session_vault(tmp_path / "vault")
    index = Index(tmp_path, root, "incremental")
    index.run()

    keys = {state.path: state.session_group_key for state in index.store.list_document_states(("main",))}

    assert keys == {
        V1_PART1_PATH: f"claude-code:{SESSION}",
        V1_PART2_PATH: f"claude-code:{SESSION}",
        V2_PART3_PATH: f"claude-code:{SESSION}",
        NOTE_PATH: None,
    }


def test_unreadable_group_member_keeps_every_v1_exchange_and_warns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = session_vault(tmp_path / "vault", with_v2=False)
    index = Index(tmp_path, root, "incremental")
    index.run()
    write(root, V2_PART3_PATH, v2_part3_text())
    original = VaultLoader.load_path

    def failing(self: VaultLoader, *, entry: object, path: str) -> object:
        if path == V1_PART2_PATH:
            raise OSError("permission denied")
        return original(self, entry=entry, path=path)  # type: ignore[arg-type]

    monkeypatch.setattr(VaultLoader, "load_path", failing)

    plan = index.run()

    assert OVERLAPPED_V1_EXCHANGES <= index.parents(V1_PART1_PATH)
    assert ("main", V1_PART2_PATH) not in plan.deleted_paths
    assert [warning for warning in plan.warnings if "session_group_incomplete" in warning] != []


def test_family_change_by_supersedes_matches_a_full_run(tmp_path: Path, reads: list[str]) -> None:
    root = tmp_path / "vault"
    write(root, "wiki/notes/a.md", "---\ntitle: A\n---\n# A\nOld fact\n")
    write(root, "wiki/notes/b.md", "---\ntitle: B\nsupersedes:\n  - wiki/notes/a.md\n---\n# B\nNew fact\n")
    write(root, "wiki/notes/c.md", "---\ntitle: C\n---\n# C\nOther\n")
    index = Index(tmp_path, root, "incremental")
    index.run()
    assert index.result() == full_result(tmp_path, root, "full-1")

    write(root, "wiki/notes/b.md", "---\ntitle: B\n---\n# B\nNew fact, no longer replacing A\n")
    reads.clear()
    index.run()

    assert sorted(reads) == ["wiki/notes/a.md", "wiki/notes/b.md"]
    assert index.result() == full_result(tmp_path, root, "full-2")

    write(root, "wiki/notes/c.md", "---\ntitle: C\nsupersedes:\n  - wiki/notes/b.md\n---\n# C\nNewest\n")
    index.run()
    assert index.result() == full_result(tmp_path, root, "full-3")


# Model token check of session windows (spec §4.2.6-11): the vector run counts session windows whose
# embedding input is over 512 model tokens and says how it counted.


def window(chunk_id: str, text: str, chunker_version: str = SESSION_EXCHANGE_V2_VERSION) -> ChunkSnapshot:
    return ChunkSnapshot(
        vault_id="main",
        chunk_id=chunk_id,
        document_id="document",
        path=f"{SESSION_DIR}/session.md",
        section="Q: question",
        anchor=None,
        text=text,
        token_count=len(text.split()),
        content_hash=f"hash:{chunk_id}",
        chunker_version=chunker_version,
        index_revision="metadata-1",
        section_path=("Session 2026-11-03 part1", "Q: question"),
    )


class ChunkStore:
    def __init__(self, chunks: tuple[ChunkSnapshot, ...]) -> None:
        self.chunks = chunks

    def list_chunks(self, scope: QueryScope) -> tuple[ChunkSnapshot, ...]:
        return self.chunks


class CountingEmbeddings(DeterministicTextEmbeddings):
    def count_model_tokens(self, text: str) -> int:
        return len(text.split())


LONG = "가나다라 " * 600  # 600 words, 7,200 UTF-8 bytes


def model_limit_warnings(embeddings: DeterministicTextEmbeddings, chunks: tuple[ChunkSnapshot, ...]) -> list[str]:
    indexer = VectorIndexer(
        chunk_store=ChunkStore(chunks), vector_store=InMemoryVectorStore(), text_embeddings=embeddings
    )
    plan = indexer.plan(scopes=(QueryScope(vault_ids=("main",), content_scopes=("raw",)),))
    return [warning for warning in plan.warnings if warning.startswith("session_window_over_model_tokens")]


def test_session_windows_over_512_tokens_are_counted_with_the_byte_estimate() -> None:
    chunks = (
        window("long-v2", LONG),
        window("long-v1", LONG, SESSION_EXCHANGE_V1_VERSION),
        window("short", "short window"),
        window("long-generic", LONG, "document-block-window-v2"),
    )

    warnings = model_limit_warnings(DeterministicTextEmbeddings(SPEC), chunks)

    assert len(warnings) == 1
    assert warnings[0].startswith("session_window_over_model_tokens: 2 session windows")
    assert warnings[0].endswith("counted with a byte estimate (UTF-8 bytes / 3)")


def test_session_windows_are_counted_with_the_model_tokenizer_when_the_provider_has_one() -> None:
    chunks = (window("long", LONG), window("mid", "단어 " * 400))

    warnings = model_limit_warnings(CountingEmbeddings(SPEC), chunks)

    assert len(warnings) == 1
    assert warnings[0].startswith("session_window_over_model_tokens: 1 session windows")
    assert warnings[0].endswith("counted with the model tokenizer")


def test_no_warning_when_every_session_window_fits() -> None:
    assert model_limit_warnings(DeterministicTextEmbeddings(SPEC), (window("short", "short window"),)) == []
