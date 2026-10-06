from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from dataclasses import replace
from pathlib import Path

import pytest

from graph_document import (
    Document,
    DocumentFeatures,
    EntityFact,
    EntityKey,
    EvidenceLocation,
    ExtractedDocument,
    ExtractionProfile,
    ExtractionResultConflictError,
    GraphDocument,
    GraphLimits,
    ItemQuery,
    LocatedValue,
    ReadLimits,
    RuleExtractor,
)

LIMITS = GraphLimits(100, 100_000, 1_000_000, 1_000, 1_000, 10_000, 1_000)
READ = ReadLimits(1_000, 1_000, 10_000, 100, 1_000_000)
PROFILE = ExtractionProfile()
SOURCE = str(Path(__file__).resolve().parents[1] / "src")


class NamedConceptExtractor:
    def extract(self, document: Document, *, profile: ExtractionProfile) -> ExtractedDocument:
        base = RuleExtractor().extract(document, profile=profile)
        concept = EntityFact(
            EntityKey("concept", "shared"),
            document.title,
            (document.title,),
            "named",
            (EvidenceLocation("document"),),
        )
        return replace(base, entities=(*base.entities, concept))


def test_aliases_follow_selected_live_contributions(tmp_path: Path) -> None:
    path = tmp_path / "graph.sqlite"
    with GraphDocument.open(
        path, mode="create", limits=LIMITS, profile=PROFILE, extractor=NamedConceptExtractor()
    ) as graph:
        graph.update_documents(
            (Document("a", "1", "Alpha", ""), Document("b", "1", "Beta", "")),
            collection_id="c",
            expected_revision=0,
        )
        all_read = graph.read(collection_id="c", selection="all", limits=READ)
        selected = graph.read(collection_id="c", selection=("b",), limits=READ)
        shared = next(node for node in all_read.nodes if node.key == "shared")
        assert shared.aliases == ("Alpha", "Beta")
        assert selected.find_items(ItemQuery("Alpha", kinds=("concept",))).items == ()
        assert (
            selected.find_items(ItemQuery("Beta", kinds=("concept",))).items[0].node_id
            == shared.node_id
        )
        graph.remove_documents(("a",), collection_id="c", expected_revision=1)
        after = graph.read(collection_id="c", selection="all", limits=READ)
        assert next(node for node in after.nodes if node.key == "shared").aliases == ("Beta",)
        assert (
            all_read.find_items(ItemQuery("Alpha", kinds=("concept",))).items[0].node_id
            == shared.node_id
        )


def test_extraction_conflict_preserves_state(tmp_path: Path) -> None:
    class ChangingExtractor:
        label = "First"

        def extract(self, document: Document, *, profile: ExtractionProfile) -> ExtractedDocument:
            base = RuleExtractor().extract(document, profile=profile)
            return replace(base, entities=(replace(base.entities[0], label=self.label),))

    extractor = ChangingExtractor()
    path = tmp_path / "graph.sqlite"
    document = Document("a", "1", "A", "")
    with GraphDocument.open(
        path, mode="create", limits=LIMITS, profile=PROFILE, extractor=extractor
    ) as graph:
        graph.update_documents((document,), collection_id="c", expected_revision=0)
        before = graph.read(collection_id="c", selection="all", limits=READ)
        extractor.label = "Second"
        with pytest.raises(ExtractionResultConflictError):
            graph.update_documents((document,), collection_id="c", expected_revision=1)
        after = graph.read(collection_id="c", selection="all", limits=READ)
        assert after.digest == before.digest
        assert after.graph_revision == 1


def test_unknown_owner_and_document_ids_are_explicit(tmp_path: Path) -> None:
    path = tmp_path / "graph.sqlite"
    with GraphDocument.open(path, mode="create", limits=LIMITS, profile=PROFILE) as graph:
        graph.update_documents(
            (Document("a", "1", "A", ""),), collection_id="c", expected_revision=0
        )
        snapshot = graph.read(collection_id="c", selection="all", limits=READ)
    lookup = snapshot.evidence_for(node_ids=("missing",), edge_ids=("missing-edge",))
    assert lookup.unknown_node_ids == ("missing",)
    assert lookup.unknown_edge_ids == ("missing-edge",)
    assert snapshot.resolve_documents(("a", "missing")).unknown_document_ids == ("missing",)


def test_two_processes_cas_one_winner(tmp_path: Path) -> None:
    path = tmp_path / "graph.sqlite"
    with GraphDocument.open(path, mode="create", limits=LIMITS, profile=PROFILE):
        pass
    script = """
import sys, time
from pathlib import Path
from graph_document import Document, ExtractionProfile, GraphDocument, GraphLimits, RevisionConflictError
path, gate, name = sys.argv[1:]
Path(gate + name).write_text('ready')
while not Path(gate).exists(): time.sleep(.002)
limits = GraphLimits(100, 100000, 1000000, 1000, 1000, 10000, 1000)
with GraphDocument.open(path, mode='read_write', limits=limits, profile=ExtractionProfile()) as graph:
    try:
        graph.update_documents((Document(name, '1', name, ''),), collection_id='c', expected_revision=0)
        print('won')
    except RevisionConflictError:
        print('conflict')
"""
    gate = str(tmp_path / "gate")
    env = {**os.environ, "PYTHONPATH": SOURCE}
    processes = [
        subprocess.Popen(
            [sys.executable, "-c", script, str(path), gate, name],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
        for name in ("a", "b")
    ]
    try:
        deadline = time.monotonic() + 10
        while not all(Path(gate + name).exists() for name in ("a", "b")):
            assert time.monotonic() < deadline
            time.sleep(0.01)
        Path(gate).write_text("go")
        outputs = [process.communicate(timeout=10) for process in processes]
        assert all(process.returncode == 0 for process in processes), outputs
        assert sorted(output.strip() for output, _ in outputs) == ["conflict", "won"]
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.wait()
    with GraphDocument.open(path, mode="read_only", limits=LIMITS, profile=PROFILE) as graph:
        snapshot = graph.read(collection_id="c", selection="all", limits=READ)
        assert snapshot.graph_revision == 1 and len(snapshot.documents) == 1


def test_reader_snapshot_overlaps_writer_commit(tmp_path: Path) -> None:
    path = tmp_path / "graph.sqlite"
    with GraphDocument.open(path, mode="create", limits=LIMITS, profile=PROFILE) as graph:
        graph.update_documents(
            (
                Document(
                    "a",
                    "source-1",
                    "A",
                    "",
                    DocumentFeatures(
                        headings=(LocatedValue("old concept", EvidenceLocation("old-heading")),)
                    ),
                ),
            ),
            collection_id="c",
            expected_revision=0,
        )

    reader_snapshot_active = threading.Event()
    allow_reader_to_finish = threading.Event()
    writer_commit_attempted = threading.Event()
    writer_finished = threading.Event()
    reader_results = []
    writer_errors: list[BaseException] = []

    def pause_after_revision_read(statement: str) -> None:
        if statement.startswith("SELECT c.document_id"):
            reader_snapshot_active.set()
            if not allow_reader_to_finish.wait(timeout=10):
                raise TimeoutError("reader was not released")

    def record_writer_commit(statement: str) -> None:
        if statement == "COMMIT":
            writer_commit_attempted.set()

    def read_snapshot() -> None:
        try:
            with GraphDocument.open(
                path, mode="read_only", limits=LIMITS, profile=PROFILE
            ) as reader:
                reader._connection.set_trace_callback(pause_after_revision_read)
                reader_results.append(reader.read(collection_id="c", selection="all", limits=READ))
        except BaseException as exc:
            writer_errors.append(exc)

    def update_document() -> None:
        try:
            with GraphDocument.open(
                path, mode="read_write", limits=LIMITS, profile=PROFILE
            ) as writer:
                writer._connection.set_trace_callback(record_writer_commit)
                writer.update_documents(
                    (
                        Document(
                            "a",
                            "source-2",
                            "A",
                            "",
                            DocumentFeatures(
                                headings=(
                                    LocatedValue("new concept", EvidenceLocation("new-heading")),
                                )
                            ),
                        ),
                    ),
                    collection_id="c",
                    expected_revision=1,
                )
        except BaseException as exc:
            writer_errors.append(exc)
        finally:
            writer_finished.set()

    reader_thread = threading.Thread(target=read_snapshot)
    writer_thread = threading.Thread(target=update_document)
    try:
        reader_thread.start()
        assert reader_snapshot_active.wait(timeout=10)
        writer_thread.start()
        assert writer_commit_attempted.wait(timeout=10)
        assert not writer_finished.wait(timeout=0.1)
    finally:
        allow_reader_to_finish.set()
        reader_thread.join(timeout=10)
        writer_thread.join(timeout=10)

    assert not reader_thread.is_alive()
    assert not writer_thread.is_alive()
    assert writer_errors == []
    assert len(reader_results) == 1
    old_snapshot = reader_results[0]
    assert old_snapshot.graph_revision == 1
    assert [(doc.document_id, doc.source_revision) for doc in old_snapshot.documents] == [
        ("a", "source-1")
    ]
    old_keys = {node.key for node in old_snapshot.nodes}
    assert "old concept" in old_keys and "new concept" not in old_keys
    assert {edge.relation_type for edge in old_snapshot.edges} == {"mentions"}
    assert old_snapshot.evidence
    assert {item.source_revision for item in old_snapshot.evidence} == {"source-1"}

    with GraphDocument.open(path, mode="read_only", limits=LIMITS, profile=PROFILE) as graph:
        new_snapshot = graph.read(collection_id="c", selection="all", limits=READ)
    assert new_snapshot.graph_revision == 2
    assert [(doc.document_id, doc.source_revision) for doc in new_snapshot.documents] == [
        ("a", "source-2")
    ]
    new_keys = {node.key for node in new_snapshot.nodes}
    assert "new concept" in new_keys and "old concept" not in new_keys
    assert {edge.relation_type for edge in new_snapshot.edges} == {"mentions"}
    assert new_snapshot.evidence
    assert {item.source_revision for item in new_snapshot.evidence} == {"source-2"}
    assert old_snapshot.graph_revision == 1
    assert {node.key for node in old_snapshot.nodes} == old_keys
    assert {item.source_revision for item in old_snapshot.evidence} == {"source-1"}


def test_killed_sqlite_transaction_reopens_at_previous_revision(tmp_path: Path) -> None:
    path = tmp_path / "graph.sqlite"
    with GraphDocument.open(path, mode="create", limits=LIMITS, profile=PROFILE) as graph:
        graph.update_documents(
            (Document("a", "1", "A", ""),), collection_id="c", expected_revision=0
        )
    marker = tmp_path / "started"
    script = """
import sqlite3, sys, time
from pathlib import Path
path, marker = sys.argv[1:]
connection = sqlite3.connect(path)
connection.execute('PRAGMA foreign_keys=ON')
connection.execute('BEGIN IMMEDIATE')
connection.execute('UPDATE collections SET graph_revision=99 WHERE collection_id=?', ('c',))
Path(marker).write_text('ready')
time.sleep(30)
"""
    process = subprocess.Popen([sys.executable, "-c", script, str(path), str(marker)])
    try:
        deadline = time.monotonic() + 10
        while not marker.exists():
            assert time.monotonic() < deadline
            time.sleep(0.01)
        process.kill()
        process.wait(timeout=10)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
    with GraphDocument.open(path, mode="read_only", limits=LIMITS, profile=PROFILE) as graph:
        snapshot = graph.read(collection_id="c", selection="all", limits=READ)
        assert snapshot.graph_revision == 1


def test_import_and_read_only_open_create_no_sidecar(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    script = """
import graph_document, sys, socket
assert 'vault_graph' not in sys.modules
assert 'graph_search' not in sys.modules
"""
    subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        cwd=empty,
        env={**os.environ, "PYTHONPATH": SOURCE},
    )
    assert list(empty.iterdir()) == []
    path = tmp_path / "graph.sqlite"
    with GraphDocument.open(path, mode="create", limits=LIMITS, profile=PROFILE) as graph:
        graph.update_documents(
            (Document("a", "1", "A", ""),), collection_id="c", expected_revision=0
        )
    before = sorted(item.name for item in tmp_path.iterdir())
    with GraphDocument.open(path, mode="read_only", limits=LIMITS, profile=PROFILE) as graph:
        graph.read(collection_id="c", selection="all", limits=READ)
    assert sorted(item.name for item in tmp_path.iterdir()) == before


def test_materialized_projection_tamper_is_detected(tmp_path: Path) -> None:
    import sqlite3

    from graph_document import StoreCorruptError

    path = tmp_path / "graph.sqlite"
    with GraphDocument.open(path, mode="create", limits=LIMITS, profile=PROFILE) as graph:
        graph.update_documents(
            (Document("a", "1", "A", ""),), collection_id="c", expected_revision=0
        )
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE nodes SET label='Altered', aliases_json='[\"Altered\"]'")
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    with GraphDocument.open(path, mode="read_only", limits=LIMITS, profile=PROFILE) as graph:
        with pytest.raises(StoreCorruptError):
            graph.read(collection_id="c", selection="all", limits=READ)
